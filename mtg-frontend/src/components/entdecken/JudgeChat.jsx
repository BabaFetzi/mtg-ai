import { useState } from 'react';
import PremiumOverlay from '../layout/PremiumOverlay';

function JudgeChat({ currentUser, userRole }) {
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
    }
    setLoading(false);
  };

  return (
    <div style={{maxWidth: '1000px', margin: '0 auto'}}>
      <div className="search-hero" style={{paddingTop: '0'}}>
        <h2>MTG Regel-Judge.</h2>
        <p>Dein KI-Schiedsrichter für Spielsituationen und Karteninteraktionen.</p>
      </div>

      <div className="judge-full-container" style={{position: 'relative'}}>
        {userRole !== 'premium' && <PremiumOverlay />}
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
        </div>
        <div className="judge-full-input">
          <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && askJudge()} placeholder="Wie löst sich dieser effekt auf...?" disabled={userRole !== 'premium'} />
          <button className="primary-btn" style={{borderRadius: '980px', padding: '0 30px'}} onClick={askJudge} disabled={userRole !== 'premium'}>Fragen</button>
        </div>
      </div>
    </div>
  );
}

export default JudgeChat;
