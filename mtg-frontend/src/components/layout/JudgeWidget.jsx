import { useState } from 'react';
import Icons from '../../utils/Icons';
import PremiumOverlay from './PremiumOverlay';
import { isPaywallResponse, handlePaywallResponse } from '../../utils/paywall';

function JudgeWidget({ open, setOpen, currentUser, userRole, onShowPremiumModal }) {
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState([{role: "judge", text: "Hallo. Ich bin der MTG Judge. Hast du eine Regelfrage zu einer Interaktion?"}]);
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
      if (isPaywallResponse(data)) {
        handlePaywallResponse(data, onShowPremiumModal);
        setChat(prev => [...prev, {role: "judge", text: "Diese Funktion ist nur für Premium-Mitglieder verfügbar. Upgrade deine Rolle im Premium-Tab, um den KI-Judge zu nutzen."}]);
      } else {
        setChat(prev => [...prev, {role: "judge", text: data.antwort}]);
      }
    } catch {
      setChat(prev => [...prev, {role: "judge", text: "Verbindungsfehler zum Judge-Netzwerk."}]);
    }
    setLoading(false);
  };

  return (
    <>
      <button
        className="judge-widget-btn"
        onClick={() => setOpen(!open)}
        title="Regelfragen klären"
        aria-label={open ? 'Rules Judge schliessen' : 'Rules Judge öffnen'}
        aria-expanded={open}
      >
        <Icons.Chat />
      </button>
      {open && (
        <div className="judge-chat-window">
          {userRole !== 'premium' && <PremiumOverlay onShowPremiumModal={onShowPremiumModal} />}
          <div className="judge-header">
            <span>Rules Judge</span>
            <button onClick={() => setOpen(false)} style={{background: 'none', border: 'none', color: 'var(--accent-text)', cursor: 'pointer', fontSize: '1.2rem'}}>✕</button>
          </div>
          <div className="judge-body">
            {(chat || []).map((m, i) => (
              <div key={i} style={{marginBottom: '15px', textAlign: m.role === 'user' ? 'right' : 'left'}}>
                <div style={{display: 'inline-block', padding: '10px 15px', borderRadius: '18px', background: m.role === 'user' ? 'var(--accent-color)' : 'var(--btn-secondary)', color: m.role === 'user' ? 'var(--accent-text)' : 'var(--text-main)', maxWidth: '85%', wordWrap: 'break-word'}}>
                  {m.text}
                </div>
              </div>
            ))}
            {loading && <div style={{textAlign: 'left'}}><span style={{display: 'inline-block', padding: '10px 15px', borderRadius: '18px', background: 'var(--btn-secondary)', color: 'var(--text-muted)'}}>Denkt nach...</span></div>}
          </div>
          <div className="judge-input-area">
            <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && askJudge()} placeholder="Frag den Judge..." disabled={userRole !== 'premium'} />
            <button onClick={askJudge} disabled={userRole !== 'premium'}><Icons.Send /></button>
          </div>
        </div>
      )}
    </>
  );
}

export default JudgeWidget;
