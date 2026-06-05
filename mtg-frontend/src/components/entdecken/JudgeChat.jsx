import { useState } from 'react';
import PremiumOverlay from '../layout/PremiumOverlay';
import { Send } from 'lucide-react';

function JudgeChat({ currentUser, userRole, onShowPremiumModal }) {
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState([{role: "judge", text: "Willkommen im offiziellen Judge-Center. Bitte beschreibe die Spielsituation oder Regelfrage so genau wie möglich."}]);
  const [loading, setLoading] = useState(false);

  const askJudge = async () => {
    if(!question.trim()) return;
    const userQ = question;
    setChat([...chat, {role: "user", text: userQ}]);
    setQuestion(""); setLoading(true);
    try {
      const res = await fetch(`/api/judge`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frage: userQ, benutzername: currentUser })
      });
      const data = await res.json();
      setChat(prev => [...prev, {role: "judge", text: data.antwort}]);
    } catch {
      setChat(prev => [...prev, {role: "judge", text: "Verbindungsfehler."}]);
    } finally {
      setLoading(false);
    }
  };

  const triggerQuickQuestion = async (qText) => {
    if(loading) return;
    setChat(prev => [...prev, {role: "user", text: qText}]);
    setLoading(true);
    try {
      const res = await fetch(`/api/judge`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frage: qText, benutzername: currentUser })
      });
      const data = await res.json();
      setChat(prev => [...prev, {role: "judge", text: data.antwort}]);
    } catch {
      setChat(prev => [...prev, {role: "judge", text: "Verbindungsfehler."}]);
    }
    setLoading(false);
  };

  return (
    <div style={{maxWidth: '1000px', margin: '0 auto'}}>
      <div className="search-hero" style={{paddingTop: '0'}}>
        <h2>MTG Rules Judge.</h2>
        <p>Dein digitaler Schiedsrichter für Spielsituationen und Karteninteraktionen.</p>
      </div>

      <div className="judge-full-container" style={{position: 'relative'}}>
        {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
        <div className="judge-full-messages">
          {(chat || []).map((m, i) => (
            <div key={i} style={{textAlign: m.role === 'user' ? 'right' : 'left'}}>
              <div style={{
                display: 'inline-block', padding: '15px 25px', borderRadius: '24px', 
                background: m.role === 'user' ? 'var(--accent-color)' : 'var(--bg-card)', 
                color: m.role === 'user' ? 'var(--accent-text)' : 'var(--text-main)', 
                maxWidth: '80%', wordWrap: 'break-word', fontSize: '1.1rem',
                border: m.role === 'judge' ? '1px solid var(--border-color)' : 'none',
                boxShadow: m.role === 'judge' ? '0 4px 15px var(--shadow-color)' : 'none'
              }}>
                {m.text}
              </div>
            </div>
          ))}
          {loading && <div style={{textAlign: 'left'}}><span style={{display: 'inline-block', padding: '15px 25px', borderRadius: '24px', background: 'var(--bg-card)', color: 'var(--text-muted)', border: '1px solid var(--border-color)'}}>Analysiere die Regeln...</span></div>}
          
          {chat.length === 1 && !loading && (
            <div style={{ marginTop: '30px', animation: 'fadeIn 0.5s ease' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', display: 'block', marginBottom: '16px', fontWeight: 600, letterSpacing: '0.05em' }}>
                Häufige Regelfragen
              </span>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '15px' }}>
                {[
                  "Wie funktioniert der Stapel (Stack)?",
                  "Wann erhalte ich Priorität?",
                  "Unterschied: Hexproof vs. Shroud",
                  "Was passiert bei Widerstandskraft 0?"
                ].map((qText) => (
                  <button
                    key={qText}
                    onClick={() => triggerQuickQuestion(qText)}
                    className="secondary-btn"
                    style={{
                      padding: '16px 20px',
                      borderRadius: '16px',
                      fontSize: '0.9rem',
                      fontWeight: 500,
                      cursor: 'pointer',
                      background: 'var(--bg-card)',
                      border: '1px solid var(--border-color)',
                      textAlign: 'left',
                      lineHeight: '1.4',
                      height: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      transition: 'transform 0.2s'
                    }}
                    onMouseEnter={e => e.currentTarget.style.transform = 'translateY(-2px)'}
                    onMouseLeave={e => e.currentTarget.style.transform = 'none'}
                  >
                    {qText}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="judge-full-input">
          <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && askJudge()} placeholder="Wie löst sich dieser Effekt auf...?" disabled={userRole !== 'premium'} />
          <button className="primary-btn" style={{borderRadius: '980px', padding: '0 30px', display: 'flex', alignItems: 'center', justifyContent: 'center'}} onClick={askJudge} disabled={userRole !== 'premium'}>
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default JudgeChat;
