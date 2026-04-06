"""
Isaac – Logic Module v2.0
===========================
Fixes gegenüber v1:
  - Semantischer Intent-Vergleich (nicht nur Keyword-Länge)
  - Multilinguale Floskel-Erkennung (de + en)
  - Ausweich-Antwort-Erkennung (auch auf Englisch)
  - Gewichtung berücksichtigt Task-Typ
  - Nachfrage-Prompts kontextspezifischer
  - Decompose-Logik produziert sauberere atomare Sub-Tasks
"""

import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

from config import get_config, LogicConfig
from audit  import AuditLog

log = logging.getLogger("Isaac.Logic")


@dataclass
class QualityScore:
    total:        float = 0.0
    length:       float = 0.0
    coverage:     float = 0.0
    specificity:  float = 0.0
    coherence:    float = 0.0
    word_count:   int   = 0
    issues:       list  = field(default_factory=list)
    strong_points: list = field(default_factory=list)

    @property
    def acceptable(self) -> bool:
        return self.total >= get_config().logic.min_quality_score

    def as_dict(self) -> dict:
        return {
            "total":       round(self.total, 2),
            "length":      round(self.length, 2),
            "coverage":    round(self.coverage, 2),
            "specificity": round(self.specificity, 2),
            "coherence":   round(self.coherence, 2),
            "word_count":  self.word_count,
            "acceptable":  self.acceptable,
            "issues":      self.issues,
        }

    def summary(self) -> str:
        icon = "✓" if self.acceptable else "✗"
        return (f"{icon} {self.total:.1f}/10 "
                f"[L:{self.length:.1f} C:{self.coverage:.1f} "
                f"S:{self.specificity:.1f} K:{self.coherence:.1f}] "
                f"({self.word_count}W)")


@dataclass
class FollowUpDecision:
    needed:          bool  = False
    mode:            str   = "none"
    followup_prompt: str   = ""
    switch_provider: bool  = False
    sub_tasks:       list  = field(default_factory=list)
    reason:          str   = ""

    def as_dict(self) -> dict:
        return {"needed": self.needed, "mode": self.mode,
                "reason": self.reason, "sub_tasks": len(self.sub_tasks)}


class TopicExtractor:
    """
    Themen-Extraktion aus Prompts.
    Sprachunabhängig durch breitere Keyword-Basis.
    """
    DOMAINS = {
        "schriften_sprachen": [
            "schrift", "alphabet", "zeichen", "symbol", "glyphe",
            "hieroglyphen", "keilschrift", "runen", "latein", "griechisch",
            "arabisch", "chinesisch", "japanisch", "devanagari", "phonetisch",
            "silbenschrift", "script", "writing", "alphabet", "glyph",
            "hieroglyph", "cuneiform", "rune", "latin", "greek", "arabic",
            "chinese", "japanese", "unicode", "charset",
        ],
        "geschichte": [
            "historisch", "antik", "mittelalter", "ancient", "ursprung",
            "entstehung", "entwicklung", "epoche", "history", "historical",
            "origin", "evolution", "era", "period", "century", "year",
        ],
        "übersetzung": [
            "übersetze", "übersetzung", "bedeutung", "heißt", "translate",
            "translation", "meaning", "means", "version", "interpret",
        ],
        "internet_recherche": [
            "suche", "finde", "recherchiere", "online", "internet",
            "webseite", "quelle", "search", "find", "research", "web",
            "google", "look up", "current", "latest", "recent",
        ],
        "technisch": [
            "code", "programm", "algorithmus", "system", "api",
            "implementier", "erstelle", "generiere", "program",
            "algorithm", "implement", "create", "generate", "build",
            "function", "class", "module",
        ],
        "analyse": [
            "analysiere", "vergleiche", "erkläre", "beschreibe", "untersuche",
            "bewerte", "beurteile", "analyze", "compare", "explain",
            "describe", "examine", "evaluate", "assess",
        ],
        "aufzählung": [
            "liste", "alle", "verschiedene", "mehrere", "zeige", "nenne",
            "list", "all", "various", "multiple", "show", "enumerate",
            "types", "arten", "examples", "beispiele",
        ],
    }

    @classmethod
    def extract(cls, text: str) -> list[str]:
        t = text.lower()
        found = []
        for domain, kws in cls.DOMAINS.items():
            if any(kw in t for kw in kws):
                found.append(domain)
        # Substantive (de + en Muster)
        for w in re.findall(r'\b[A-ZÄÖÜ][a-zäöüßa-z]{3,}\b', text)[:6]:
            wl = w.lower()
            if wl not in {"isaac", "steffen", "claude"}:
                found.append(wl)
        if re.search(r'\b(wer|was|wie|warum|wann|wo|welche|who|what|how|why|when|where|which)\b', t):
            found.append("frage_erwartet")
        return list(dict.fromkeys(found))   # Reihenfolge erhalten, Duplikate entfernen


class QualityEvaluator:
    """
    Bewertet Antwortqualität auf 0–10.
    Multilingual. Erkennt semantische Ausweichung.
    """

    # Ausweich-Phrasen die auf eine schlechte Antwort hinweisen
    AUSWEICH_DE = [
        "als ki kann ich", "als sprachmodell", "ich bin nicht in der lage",
        "das kann ich nicht", "leider kann ich", "ich habe keinen zugriff",
        "meine kenntnisse reichen", "das liegt außerhalb",
    ]
    AUSWEICH_EN = [
        "as an ai", "as a language model", "i'm not able to", "i cannot",
        "i don't have access", "my knowledge", "that's outside",
        "i'm unable to", "i apologize", "i can't help",
    ]
    VAGE_DE = [
        "allgemein", "grundsätzlich", "im großen und ganzen",
        "in gewisser weise", "man könnte sagen", "irgendwie",
        "es kommt darauf an", "das ist komplex",
    ]
    VAGE_EN = [
        "generally speaking", "it depends", "various things",
        "in some ways", "one could say", "it's complex",
        "there are many", "it varies",
    ]
    CONNECTOR_DE = [
        "daher", "deshalb", "außerdem", "jedoch", "einerseits",
        "andererseits", "zunächst", "schließlich", "erstens", "zweitens",
        "zudem", "darüber hinaus", "insbesondere",
    ]
    CONNECTOR_EN = [
        "therefore", "however", "additionally", "furthermore", "firstly",
        "secondly", "moreover", "in contrast", "specifically", "notably",
        "consequently", "thus",
    ]

    def __init__(self):
        self.cfg: LogicConfig = get_config().logic

    def evaluate(self, antwort: str, prompt: str,
                 themen: list[str] = None) -> QualityScore:
        if not antwort or antwort.startswith("[RELAY"):
            return QualityScore(total=0.0, issues=["Fehler-Antwort oder leer"])

        # Ausweich-Erkennung zuerst — sofortiger Malus
        ausweich = self._detect_evasion(antwort)

        score         = QualityScore()
        score.word_count = len(antwort.split())
        themen        = themen or TopicExtractor.extract(prompt)

        score.length      = self._score_length(score.word_count)
        score.coverage    = self._score_coverage(antwort, themen, prompt)
        score.specificity = self._score_specificity(antwort)
        score.coherence   = self._score_coherence(antwort)

        if ausweich:
            score.specificity = max(0.0, score.specificity - 3.0)
            score.issues.append(f"Ausweich-Antwort: {ausweich}")

        self._detect_issues(score, antwort, prompt, themen)

        cfg = self.cfg
        score.total = min(10.0, max(0.0,
            score.length      * cfg.weight_length +
            score.coverage    * cfg.weight_coverage +
            score.specificity * cfg.weight_specificity +
            score.coherence   * cfg.weight_coherence
        ))
        return score

    def _detect_evasion(self, text: str) -> str:
        t = text.lower()
        for phrase in self.AUSWEICH_DE + self.AUSWEICH_EN:
            if phrase in t:
                return phrase
        return ""

    def _score_length(self, n: int) -> float:
        m = self.cfg.min_word_count
        if n < 10:       return 0.0
        if n < m * 0.25: return 1.5
        if n < m * 0.5:  return 3.5
        if n < m:        return 6.0
        if n < m * 2:    return 8.0
        if n < m * 4:    return 9.5
        return 10.0

    def _score_coverage(self, text: str, themen: list, prompt: str) -> float:
        if not themen:
            return 6.0
        t = text.lower()
        p_words = set(w for w in re.findall(r'\w{4,}', prompt.lower())
                      if w not in {"bitte", "kannst", "please", "could", "would"})

        abgedeckt = 0.0
        for thema in themen:
            basis = thema.split("_")[0]
            if basis in t or thema in t:
                abgedeckt += 1.0
            elif any(w in t for w in thema.split("_")):
                abgedeckt += 0.5

        ratio = abgedeckt / len(themen)

        # Prompt-Schlüsselwörter in Antwort
        p_coverage = (sum(1 for w in p_words if w in t) /
                      max(len(p_words), 1))

        # Semantischer Intent-Vergleich:
        # Wenn Prompt "liste" oder "alle" enthält → prüfe ob Antwort Aufzählungen hat
        if "aufzählung" in themen:
            hat_liste = bool(re.search(r'(\n[-•*]\s|\n\d+\.|\n[A-Z])', text))
            if not hat_liste:
                ratio *= 0.6

        combined = ratio * 0.65 + p_coverage * 0.35
        return round(min(10.0, combined * 10), 1)

    def _score_specificity(self, text: str) -> float:
        score = 5.0
        t = text.lower()

        # Positive Signale
        if re.search(r'\b\d{4}\b', text):              score += 0.8   # Jahreszahlen
        if re.search(r'\b\d+[.,]\d+', text):           score += 0.5   # Dezimalzahlen
        if re.search(r'\b\d+\s*(km|m|kg|hz|mb|gb|%)', t): score += 0.5
        if text.count('\n') >= 3:                       score += 0.5   # Strukturiert
        if re.search(r'[-•*]\s.{10,}', text):          score += 0.6   # Aufzählung
        if re.search(r'^\d+\.\s.{10,}', text, re.M):  score += 0.6   # Nummeriert
        if re.search(r':\s', text):                    score += 0.3   # Doppelpunkt-Erklärungen
        if re.search(r'["„»].{5,}["«"]', text):        score += 0.4   # Zitate
        if re.search(r'https?://\S+', text):            score += 0.4   # URLs als Belege

        # Beispiele (de + en)
        if re.search(r'\b(z\.B\.|zum Beispiel|beispielsweise|'
                     r'for example|e\.g\.|such as|like)\b', text, re.I):
            score += 0.8

        # Vage Floskeln abziehen (de + en)
        for phrase in self.VAGE_DE + self.VAGE_EN:
            if phrase in t:
                score -= 0.25

        # Zu kurz → immer niedrig
        if len(text.split()) < 30:
            score -= 2.5

        return max(0.0, min(10.0, score))

    def _score_coherence(self, text: str) -> float:
        sätze = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 8]
        if len(sätze) < 2:
            return 3.5

        score = 7.0
        t = text.lower()

        # Verbindungswörter (de + en)
        c_count = sum(1 for w in self.CONNECTOR_DE + self.CONNECTOR_EN if w in t)
        score += min(2.0, c_count * 0.35)

        # Strukturierung
        if re.search(r'^#{1,3}\s', text, re.M): score += 0.5
        if re.search(r'^\d+\.\s', text, re.M):  score += 0.5
        if re.search(r'^[-•*]\s', text, re.M):  score += 0.3

        # Wiederholungen bestrafen
        words = text.lower().split()
        if len(words) > 30:
            freq = {}
            for w in words:
                if len(w) > 6:
                    freq[w] = freq.get(w, 0) + 1
            max_f = max(freq.values(), default=1)
            if max_f > len(words) * 0.06:
                score -= 1.5

        return max(0.0, min(10.0, score))

    def _detect_issues(self, score: QualityScore, text: str,
                       prompt: str, themen: list):
        if score.word_count < self.cfg.min_word_count:
            score.issues.append(
                f"Zu kurz: {score.word_count}/{self.cfg.min_word_count} Wörter"
            )
        if score.coverage < 5.0:
            score.issues.append("Schlüsselthemen nicht vollständig abgedeckt")
        if score.specificity < 4.0:
            score.issues.append("Antwort zu vage — keine konkreten Details")
        if score.coherence < 4.5:
            score.issues.append("Schwache Struktur oder Kohärenz")
        if score.total >= 8.0:
            score.strong_points.append("Vollständige, gut strukturierte Antwort")
        if score.specificity >= 8.5:
            score.strong_points.append("Sehr präzise und detailreich")


class FollowUpGenerator:
    def __init__(self, evaluator: QualityEvaluator):
        self.ev  = evaluator
        self.cfg = get_config().logic

    def decide(self, antwort: str, prompt: str, score: QualityScore,
               iteration: int, provider: str = "") -> FollowUpDecision:
        d = FollowUpDecision()
        if iteration >= self.cfg.max_followup_rounds:
            d.reason = "Max Iterationen"
            return d
        if score.acceptable:
            d.reason = "Qualität ok"
            return d

        d.needed = True
        themen   = TopicExtractor.extract(prompt)

        # Entscheidungsbaum
        if score.total <= self.cfg.instance_switch_score:
            d.mode            = "switch"
            d.switch_provider = True
            d.reason          = f"Score {score.total:.1f} unter Switch-Schwelle {self.cfg.instance_switch_score}"
            d.followup_prompt = self._targeted(prompt, score, themen)

        elif "aufzählung" in themen and score.coverage < 5.5:
            d.mode      = "decompose"
            d.sub_tasks = self._decompose(prompt, themen)
            d.reason    = "Aufzählung unvollständig"

        elif score.length < 4.5:
            d.mode            = "rephrase"
            d.followup_prompt = self._extend(prompt, score)
            d.reason          = f"Zu kurz ({score.word_count} Wörter)"

        elif score.coverage < 5.0:
            d.mode            = "targeted"
            d.followup_prompt = self._targeted(prompt, score, themen)
            d.reason          = "Coverage ungenügend"

        else:
            d.mode            = "rephrase"
            d.followup_prompt = self._detail(prompt, antwort, score)
            d.reason          = f"Gesamt-Score {score.total:.1f} unter Minimum"

        return d

    def _targeted(self, prompt: str, score: QualityScore, themen: list) -> str:
        fehler = score.issues[:3]
        msg    = (f"Beantworte diese Aufgabe ausführlicher und vollständiger:\n\n"
                  f"{prompt}\n\n")
        if fehler:
            msg += "Folgende Punkte wurden nicht ausreichend behandelt:\n"
            msg += "".join(f"- {f}\n" for f in fehler)
        msg += ("\nAnforderungen:\n"
                "- Mindestens 200 Wörter\n"
                "- Konkrete Beispiele und Fakten\n"
                "- Klare Struktur (Absätze oder Aufzählung)\n"
                "- Keine allgemeinen Floskeln")
        return msg

    def _extend(self, prompt: str, score: QualityScore) -> str:
        min_w = self.cfg.min_word_count * 2
        return (f"Diese Aufgabe benötigt eine deutlich ausführlichere Antwort:\n\n"
                f"{prompt}\n\n"
                f"Deine Antwort hatte nur {score.word_count} Wörter. "
                f"Liefere mindestens {min_w} Wörter. "
                f"Erkläre jeden Aspekt gründlich mit konkreten Details.")

    def _detail(self, prompt: str, antwort: str, score: QualityScore) -> str:
        kurz = antwort[:200] + "..." if len(antwort) > 200 else antwort
        return (f"Erste Antwort:\n---\n{kurz}\n---\n\n"
                f"Ursprüngliche Aufgabe:\n{prompt}\n\n"
                f"Geh jetzt erheblich tiefer ins Detail. Füge Fakten, "
                f"Beispiele, Vergleiche und strukturierte Erklärungen hinzu.")

    def _decompose(self, prompt: str, themen: list) -> list[str]:
        ignore = {"frage_erwartet", "aufzählung", "internet_recherche",
                  "analyse", "übersetzung"}
        subs = []
        for t in themen:
            if t not in ignore:
                subs.append(
                    f"Recherchiere und erkläre ausführlich: "
                    f"{t.replace('_', ' ')} "
                    f"(Kontext: {prompt[:80]})"
                )
        if not subs:
            subs = [
                f"Hintergrund und Ursprung: {prompt[:100]}",
                f"Eigenschaften und Details: {prompt[:100]}",
                f"Beispiele und Anwendungen: {prompt[:100]}",
            ]
        return subs[:4]


class LogicModule:
    def __init__(self):
        self.evaluator = QualityEvaluator()
        self.followup  = FollowUpGenerator(self.evaluator)
        self.cfg       = get_config().logic
        self._stats    = {
            "total_evaluated":     0,
            "followups_generated": 0,
            "switches":            0,
            "decompositions":      0,
        }
        log.info("LogicModule v2.0 online")

    def evaluate(self, antwort: str, prompt: str, task_id: str = "") -> QualityScore:
        score = self.evaluator.evaluate(antwort, prompt)
        self._stats["total_evaluated"] += 1
        AuditLog.quality(task_id, score.total, score.as_dict(), 0, "evaluated")
        log.debug(f"[Logic] {score.summary()}")
        return score

    def decide_followup(self, antwort: str, prompt: str, score: QualityScore,
                        iteration: int, provider: str = "",
                        task_id: str = "") -> FollowUpDecision:
        d = self.followup.decide(antwort, prompt, score, iteration, provider)
        if d.needed:
            self._stats["followups_generated"] += 1
            if d.switch_provider: self._stats["switches"] += 1
            if d.mode == "decompose": self._stats["decompositions"] += 1
        AuditLog.quality(task_id, score.total, score.as_dict(), iteration,
                         f"followup:{d.mode}" if d.needed else "accepted")
        if d.needed:
            log.info(f"[Logic] Nachfrage │ {d.mode} │ {d.reason}")
        return d

    def extract_topics(self, text: str) -> list[str]:
        return TopicExtractor.extract(text)

    def stats(self) -> dict:
        return {**self._stats, "cfg": {
            "min_score":  self.cfg.min_quality_score,
            "max_rounds": self.cfg.max_followup_rounds,
            "min_words":  self.cfg.min_word_count,
        }}


_logic: Optional[LogicModule] = None

def get_logic() -> LogicModule:
    global _logic
    if _logic is None:
        _logic = LogicModule()
    return _logic
