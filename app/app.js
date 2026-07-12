// Isaac Web App - Chat Interface mit WebSocket

class IsaacApp {
    constructor() {
        this.wsUrl = 'ws://localhost:5000/ws'; // WebSocket URL
        this.ws = null;
        this.chatWindow = document.getElementById('chatWindow');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.conversationHistory = [];
        this.connectionStatus = 'disconnected';
        
        this.init();
    }
    
    init() {
        // Event Listener für UI
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Lokale Speicherung laden
        this.loadConversation();
        
        // WebSocket verbinden
        this.connectWebSocket();
    }
    
    connectWebSocket() {
        try {
            this.ws = new WebSocket(this.wsUrl);
            
            this.ws.onopen = () => {
                console.log('✅ WebSocket verbunden');
                this.connectionStatus = 'connected';
                this.updateConnectionStatus();
                this.addSystemMessage('✅ Verbunden mit Isaac Backend');
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('📨 Nachricht empfangen:', data);
                    
                    if (data.type === 'response') {
                        this.addMessage('isaac', data.message);
                    } else if (data.type === 'error') {
                        this.addMessage('isaac', `⚠️ Fehler: ${data.message}`);
                    } else if (data.type === 'status') {
                        this.addSystemMessage(data.message);
                    }
                } catch (e) {
                    console.error('JSON Parse Fehler:', e);
                }
            };
            
            this.ws.onerror = (error) => {
                console.error('❌ WebSocket Fehler:', error);
                this.connectionStatus = 'error';
                this.updateConnectionStatus();
                this.addSystemMessage('⚠️ Verbindungsfehler - versuche erneut...');
            };
            
            this.ws.onclose = () => {
                console.log('🔌 WebSocket getrennt');
                this.connectionStatus = 'disconnected';
                this.updateConnectionStatus();
                this.addSystemMessage('🔌 Verbindung unterbrochen - versuche zu reconnecten...');
                // Automatisches Reconnect nach 3 Sekunden
                setTimeout(() => this.connectWebSocket(), 3000);
            };
            
        } catch (error) {
            console.error('WebSocket Verbindungsfehler:', error);
            this.connectionStatus = 'error';
            this.updateConnectionStatus();
        }
    }
    
    sendMessage() {
        const text = this.messageInput.value.trim();
        if (!text) return;
        if (this.connectionStatus !== 'connected') {
            this.addSystemMessage('⚠️ Nicht verbunden - warte auf Verbindung...');
            return;
        }
        
        // Benutzer-Nachricht anzeigen
        this.addMessage('user', text);
        this.messageInput.value = '';
        this.messageInput.focus();
        
        // Loading-Indikator
        this.sendBtn.disabled = true;
        this.sendBtn.textContent = '⏳';
        
        try {
            // An Backend über WebSocket senden
            const payload = {
                type: 'message',
                content: text,
                history: this.conversationHistory
            };
            
            this.ws.send(JSON.stringify(payload));
            console.log('📤 Nachricht gesendet:', payload);
            
        } catch (error) {
            console.error('Fehler beim Senden:', error);
            this.addMessage('isaac', `❌ Fehler beim Senden: ${error.message}`);
        } finally {
            this.sendBtn.disabled = false;
            this.sendBtn.textContent = 'Senden';
        }
    }
    
    addMessage(sender, text) {
        const messageEl = document.createElement('div');
        messageEl.classList.add('message', sender);
        messageEl.textContent = text;
        this.chatWindow.appendChild(messageEl);
        
        // Speichern
        this.conversationHistory.push({ 
            sender, 
            text, 
            timestamp: new Date().toISOString()
        });
        this.saveConversation();
        
        // Scrollen nach unten
        this.chatWindow.scrollTop = this.chatWindow.scrollHeight;
    }
    
    addSystemMessage(text) {
        const messageEl = document.createElement('div');
        messageEl.classList.add('message', 'system');
        messageEl.textContent = text;
        messageEl.style.opacity = '0.7';
        messageEl.style.fontSize = '0.85rem';
        messageEl.style.textAlign = 'center';
        this.chatWindow.appendChild(messageEl);
        this.chatWindow.scrollTop = this.chatWindow.scrollHeight;
    }
    
    updateConnectionStatus() {
        const statusIndicator = document.querySelector('.status-indicator') || this.createStatusIndicator();
        
        if (this.connectionStatus === 'connected') {
            statusIndicator.textContent = '🟢 Verbunden';
            statusIndicator.style.color = '#10b981';
        } else if (this.connectionStatus === 'disconnected') {
            statusIndicator.textContent = '🔴 Getrennt';
            statusIndicator.style.color = '#ef4444';
        } else {
            statusIndicator.textContent = '🟡 Fehler';
            statusIndicator.style.color = '#f59e0b';
        }
    }
    
    createStatusIndicator() {
        const indicator = document.createElement('div');
        indicator.className = 'status-indicator';
        indicator.style.position = 'fixed';
        indicator.style.bottom = '1rem';
        indicator.style.right = '1rem';
        indicator.style.padding = '0.5rem 1rem';
        indicator.style.background = '#1e293b';
        indicator.style.borderRadius = '20px';
        indicator.style.fontSize = '0.85rem';
        indicator.style.zIndex = '999';
        document.body.appendChild(indicator);
        return indicator;
    }
    
    saveConversation() {
        localStorage.setItem('isaac_conversation', JSON.stringify(this.conversationHistory));
    }
    
    loadConversation() {
        const saved = localStorage.getItem('isaac_conversation');
        if (saved) {
            this.conversationHistory = JSON.parse(saved);
            this.conversationHistory.forEach(msg => {
                if (msg.sender !== 'system') {
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
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

// App starten
document.addEventListener('DOMContentLoaded', () => {
    window.isaac = new IsaacApp();
});

// Cleanup beim Verlassen
window.addEventListener('beforeunload', () => {
    if (window.isaac) {
        window.isaac.disconnect();
    }
});

// Tastenkombination: Ctrl+Shift+X zum Löschen
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'X') {
        if (window.isaac) {
            window.isaac.clearConversation();
        }
    }
});
