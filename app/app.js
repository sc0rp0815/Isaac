// Isaac Web App - Chat Interface

class IsaacApp {
    constructor() {
        this.apiUrl = 'http://localhost:5000'; // Anpassbar für deinen Python-Server
        this.chatWindow = document.getElementById('chatWindow');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.conversationHistory = [];
        
        this.init();
    }
    
    init() {
        // Event Listener
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Lokale Speicherung laden
        this.loadConversation();
        
        // Willkommensnachricht
        this.addMessage('isaac', 'Hallo! Ich bin Isaac. Wie kann ich dir heute helfen?');
    }
    
    addMessage(sender, text) {
        const messageEl = document.createElement('div');
        messageEl.classList.add('message', sender);
        messageEl.textContent = text;
        this.chatWindow.appendChild(messageEl);
        
        // Speichern
        this.conversationHistory.push({ sender, text, timestamp: Date.now() });
        this.saveConversation();
        
        // Scrollen nach unten
        this.chatWindow.scrollTop = this.chatWindow.scrollHeight;
    }
    
    async sendMessage() {
        const text = this.messageInput.value.trim();
        if (!text) return;
        
        // Benutzer-Nachricht anzeigen
        this.addMessage('user', text);
        this.messageInput.value = '';
        this.messageInput.focus();
        
        // Loading-Indikator
        this.sendBtn.disabled = true;
        this.sendBtn.textContent = 'Wird gesendet...';
        
        try {
            // An Python-Backend senden
            const response = await fetch(`${this.apiUrl}/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    history: this.conversationHistory
                })
            });
            
            if (!response.ok) {
                throw new Error('Backend-Verbindung fehlgeschlagen');
            }
            
            const data = await response.json();
            this.addMessage('isaac', data.response);
            
        } catch (error) {
            console.error('Fehler:', error);
            this.addMessage('isaac', `⚠️ Fehler: ${error.message}. Backend-Server läuft nicht?`);
        } finally {
            this.sendBtn.disabled = false;
            this.sendBtn.textContent = 'Senden';
        }
    }
    
    saveConversation() {
        localStorage.setItem('isaac_conversation', JSON.stringify(this.conversationHistory));
    }
    
    loadConversation() {
        const saved = localStorage.getItem('isaac_conversation');
        if (saved) {
            this.conversationHistory = JSON.parse(saved);
            // Konversation anzeigen (ohne Willkommensnachricht)
            this.conversationHistory.forEach(msg => {
                if (!(msg.sender === 'isaac' && msg.text === 'Hallo! Ich bin Isaac. Wie kann ich dir heute helfen?')) {
                    const messageEl = document.createElement('div');
                    messageEl.classList.add('message', msg.sender);
                    messageEl.textContent = msg.text;
                    this.chatWindow.appendChild(messageEl);
                }
            });
        }
    }
    
    clearConversation() {
        if (confirm('Konversation wirklich löschen?')) {
            this.conversationHistory = [];
            this.chatWindow.innerHTML = '';
            localStorage.removeItem('isaac_conversation');
            this.addMessage('isaac', 'Konversation gelöscht. Neuer Start!');
        }
    }
}

// App starten
document.addEventListener('DOMContentLoaded', () => {
    window.isaac = new IsaacApp();
});

// Tastenkombination: Ctrl+Shift+X zum Löschen
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'X') {
        window.isaac.clearConversation();
    }
});