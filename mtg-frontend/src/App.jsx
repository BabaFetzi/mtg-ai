import { useState, useEffect } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'

// Components
import AuthScreen from './components/auth/AuthScreen'
import AppleHeader from './components/layout/AppleHeader'
import EntdeckenHub from './components/entdecken/EntdeckenHub'
import MeineSammlung from './components/sammlung/MeineSammlung'
import DecksView from './components/decks/DecksView'
import PremiumPage from './components/premium/PremiumPage'
import JudgeWidget from './components/layout/JudgeWidget'

const globalStyles = `
/* --- THEME VARIABLES (Harmonisiert & Pro) --- */
:root {
  --bg-main: #FBFBFD;
  --bg-card: #FFFFFF;
  --text-main: #1D1D1F;
  --text-muted: #86868B;
  --border-color: #E5E5EA;
  --nav-bg: rgba(255, 255, 255, 0.7);
  --input-bg: #FFFFFF;
  --btn-secondary: #F5F5F7;
  --btn-secondary-hover: #E5E5EA;
  --shadow-color: rgba(0,0,0,0.04);
  
  --accent-color: #1D1D1F;
  --accent-text: #FFFFFF;
  --accent-hover: #333336;
  
  --price-color: #1E823C; 
  --danger-color: #C93B3B;
  --danger-bg: rgba(201, 59, 59, 0.08);
}

.dark-mode {
  --bg-main: #000000;
  --bg-card: #1C1C1E;
  --text-main: #F5F5F7;
  --text-muted: #98989D;
  --border-color: #38383A;
  --nav-bg: rgba(28, 28, 30, 0.7);
  --input-bg: #2C2C2E;
  --btn-secondary: #2C2C2E;
  --btn-secondary-hover: #3A3A3C;
  --shadow-color: rgba(0,0,0,0.3);
  
  --accent-color: #F5F5F7;
  --accent-text: #1D1D1F;
  --accent-hover: #D1D1D6;
  
  --price-color: #30B058;
  --danger-color: #E05252;
  --danger-bg: rgba(224, 82, 82, 0.12);
}

#root { max-width: 100% !important; width: 100% !important; margin: 0 !important; padding: 0 !important; text-align: left !important; }

body {
  margin: 0; padding: 0;
  background-color: var(--bg-main); 
  color: var(--text-main);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased; padding-top: 60px;
  transition: background-color 0.3s ease, color 0.3s ease;
}

h1, h2, h3, h4 { font-weight: 600; letter-spacing: -0.015em; margin: 0 0 16px 0; line-height: 1.2; color: var(--text-main); }
h2 { font-size: 2.5rem; letter-spacing: -0.03em; }
p { color: var(--text-muted); line-height: 1.5; margin: 0 0 16px 0; }

/* --- APPLE MEGA MENU NAVIGATION --- */
.apple-nav-container { 
  position: fixed; top: 0; left: 0; width: 100%; 
  background: var(--nav-bg); 
  backdrop-filter: saturate(180%) blur(20px); -webkit-backdrop-filter: saturate(180%) blur(20px); 
  border-bottom: 1px solid var(--border-color); z-index: 9999; display: flex; justify-content: center; 
  transition: background 0.3s ease; 
}
.apple-nav-container.menu-open { background: var(--bg-card); }

.apple-nav-list { 
  display: flex; gap: 30px; list-style: none; margin: 0; padding: 0; height: 50px; align-items: center; 
  width: 100%; max-width: 1000px; justify-content: space-between; 
}
.apple-nav-item { height: 100%; display: flex; align-items: center; }
.apple-nav-link { 
  color: var(--text-main); text-decoration: none; font-size: 0.75rem; padding: 0 10px; 
  cursor: pointer; transition: opacity 0.2s; opacity: 0.8; font-weight: 400; 
}
.apple-nav-link:hover { opacity: 1; }
.theme-toggle { background: none; border: none; cursor: pointer; padding: 5px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: var(--text-main); opacity: 0.8; transition: opacity 0.2s; }
.theme-toggle:hover { opacity: 1; }

.global-mega-menu {
  position: absolute; top: 50px; left: 0; width: 100%;
  background: var(--bg-card); box-shadow: 0 20px 40px var(--shadow-color);
  border-bottom: 1px solid var(--border-color); height: 0; overflow: hidden;
  transition: height 0.4s cubic-bezier(0.25, 1, 0.5, 1), opacity 0.3s;
  z-index: 9998; opacity: 0; pointer-events: none;
}
.global-mega-menu.open { height: 320px; opacity: 1; pointer-events: auto; }

.mega-menu-inner { max-width: 1000px; margin: 0 auto; padding: 0 10px; position: relative; height: 100%; }

.mega-content-panel {
  display: flex; gap: 80px; position: absolute; top: 50px; left: 10px; width: 100%;
  opacity: 0; visibility: hidden; transform: translateX(-15px);
  transition: opacity 0.3s ease, transform 0.3s ease, visibility 0.3s;
}
.mega-content-panel.active { opacity: 1; visibility: visible; transform: translateX(0); transition-delay: 0.15s; }

.dropdown-column { display: flex; flex-direction: column; gap: 12px; text-align: left; }
.dropdown-column h4 { font-size: 0.75rem; color: var(--text-muted); font-weight: 400; margin: 0; letter-spacing: 0; }
.dropdown-column a { display: block; color: var(--text-main); text-decoration: none; font-size: 1.5rem; font-weight: 600; cursor: pointer; transition: color 0.2s; letter-spacing: -0.01em;}
.dropdown-column a:hover { color: var(--text-muted); }

/* --- CONTAINERS & CARDS --- */
.apple-main-container { max-width: 1600px; margin: 0 auto; padding: 50px 4%; }
.content-card { background: var(--bg-card); border-radius: 24px; padding: 40px; box-shadow: 0 8px 30px var(--shadow-color); text-align: left; margin-bottom: 24px; border: 1px solid var(--border-color); transition: background-color 0.3s, border-color 0.3s; }

input, textarea, select {
  width: 100%; background: var(--input-bg); border: 1px solid var(--border-color); color: var(--text-main);
  padding: 16px 20px; border-radius: 12px; font-size: 1.05rem; box-sizing: border-box; transition: all 0.2s; font-family: inherit;
}
input:focus, textarea:focus, select:focus { outline: none; border-color: #0071E3; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.1); }

.primary-btn { background: var(--accent-color); color: var(--accent-text); border: none; padding: 14px 28px; border-radius: 980px; font-size: 1.05rem; font-weight: 500; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 8px;}
.primary-btn:hover { background: var(--accent-hover); }
.secondary-btn { background: var(--btn-secondary); color: var(--text-main); border: none; padding: 14px 28px; border-radius: 980px; font-size: 1.05rem; font-weight: 500; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none;}
.secondary-btn:hover { background: var(--btn-secondary-hover); }

.market-btn { background: var(--price-color); color: white; border: none; padding: 14px 28px; border-radius: 980px; font-size: 1.05rem; font-weight: 500; cursor: pointer; transition: opacity 0.2s; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
.market-btn:hover { opacity: 0.8; }
.danger-btn-subtle { background: transparent; color: var(--danger-color); border: none; padding: 8px 16px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.danger-btn-subtle:hover { background: var(--danger-bg); }

/* --- KARTEN SUCHE LAYOUT --- */
.search-hero { text-align: center; padding: 60px 0 40px; }
.search-hero h2 { font-size: 3.5rem; letter-spacing: -0.04em; margin-bottom: 15px; line-height: 1.1; }
.search-hero p { font-size: 1.2rem; color: var(--text-muted); }
.search-bar-wrapper { display: flex; gap: 15px; max-width: 800px; margin: 0 auto 50px auto; }
.result-layout { display: grid; grid-template-columns: 420px 1fr; gap: 80px; align-items: start; }
@media (max-width: 1050px) { .result-layout { grid-template-columns: 1fr; gap: 40px; } }
.card-image-wrapper { position: sticky; top: 100px; }
.main-card-img { width: 100%; max-width: 420px; border-radius: 4.75% / 3.5%; box-shadow: 0 25px 60px rgba(0,0,0,0.3); margin-bottom: 25px; display: block; }
.prints-scroll { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 15px; scrollbar-width: thin; }
.print-thumb { width: 80px; flex-shrink: 0; border-radius: 4.75% / 3.5%; cursor: pointer; opacity: 0.4; transition: all 0.2s; box-shadow: 0 4px 10px rgba(0,0,0,0.2); border: 2px solid transparent; }
.print-thumb:hover { opacity: 0.8; transform: translateY(-3px); }
.print-thumb.active { opacity: 1; border-color: var(--accent-color); transform: translateY(-3px); }
.info-header { border-bottom: 1px solid var(--border-color); padding-bottom: 25px; margin-bottom: 30px; }
.info-header h3 { font-size: 3.2rem; margin: 0 0 12px 0; letter-spacing: -0.02em; line-height: 1.1; }
.info-header p { font-size: 1.3rem; color: var(--text-muted); margin: 0; line-height: 1.5; }
.translation-box { background: var(--btn-secondary); padding: 30px; border-radius: 20px; margin-bottom: 30px; border: 1px solid var(--border-color); }
.price-display { font-size: 3.8rem; color: var(--price-color); font-weight: 600; letter-spacing: -0.04em; margin: 0; line-height: 1; }

/* --- TRENDING CARDS --- */
.trending-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 30px; margin-top: 20px; }
.trending-item { position: relative; border-radius: 4.75% / 3.5%; overflow: hidden; box-shadow: 0 10px 30px var(--shadow-color); cursor: pointer; transition: transform 0.3s, box-shadow 0.3s; }
.trending-item:hover { transform: translateY(-8px); box-shadow: 0 20px 40px rgba(0,0,0,0.2); }
.trending-item img { width: 100%; display: block; }
.trending-overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.6); display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.3s; backdrop-filter: blur(2px); }
.trending-item:hover .trending-overlay { opacity: 1; }
.trending-overlay span { color: white; font-weight: 600; font-size: 1.1rem; border: 2px solid white; padding: 8px 16px; border-radius: 20px; }

/* --- SYNERGY VIEW & COMBO IMAGES --- */
.synergy-combo-card { background: var(--btn-secondary); padding: 25px; border-radius: 20px; margin-bottom: 20px; border: 1px solid var(--border-color); transition: transform 0.2s; }
.synergy-combo-card:hover { transform: translateX(5px); border-color: #0071E3; }
.tournament-combo-card { background: linear-gradient(145deg, var(--bg-card) 0%, var(--btn-secondary) 100%); border: 1px solid var(--border-color); padding: 35px; border-radius: 24px; box-shadow: 0 10px 30px var(--shadow-color); transition: transform 0.2s; margin-bottom: 30px; }
.tournament-combo-card:hover { transform: translateY(-5px); border-color: var(--accent-color); }
.combo-badge { display: inline-block; background: var(--accent-color); color: var(--accent-text); padding: 6px 14px; border-radius: 8px; font-size: 0.85rem; font-weight: 600; margin-bottom: 20px; }

.combo-images-container { display: flex; margin-bottom: 30px; padding: 20px 0 20px 20px; align-items: center; }
.combo-card-img { 
  width: 130px; border-radius: 4.75% / 3.5%; 
  box-shadow: 0 8px 20px rgba(0,0,0,0.25); 
  transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275); 
  margin-right: -60px; 
  border: 2px solid var(--bg-card);
  background: var(--bg-main);
  position: relative;
  z-index: 1;
  transform-origin: center center;
}
.combo-card-img:hover { 
  transform: scale(2.4) translateY(-10px); 
  z-index: 100; 
  margin-right: 70px;
  margin-left: 70px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.6);
}
.combo-card-img:last-child { margin-right: 0; }
.combo-card-img:last-child:hover { margin-right: 0; margin-left: 70px; }

/* --- JUDGE FULL VIEW & RULES --- */
.judge-full-container { display: flex; flex-direction: column; height: 650px; background: var(--btn-secondary); border-radius: 24px; border: 1px solid var(--border-color); overflow: hidden; }
.judge-full-messages { flex-grow: 1; overflow-y: auto; padding: 30px; display: flex; flex-direction: column; gap: 20px; }
.judge-full-input { display: flex; padding: 20px; background: var(--bg-card); border-top: 1px solid var(--border-color); gap: 15px; }
.judge-full-input input { flex-grow: 1; border-radius: 980px; padding: 18px 25px; }

.rule-card { background: var(--bg-card); border: 1px solid var(--border-color); padding: 25px; border-radius: 16px; margin-bottom: 15px; box-shadow: 0 4px 15px var(--shadow-color); transition: border-color 0.2s; }
.rule-card:hover { border-color: var(--accent-color); }
.rule-card h4 { margin: 0 0 10px 0; color: var(--text-main); font-size: 1.2rem; }
.rule-card p { margin: 0; color: var(--text-muted); font-size: 1.05rem; line-height: 1.6;}
.rule-id { font-family: monospace; color: #0071E3; font-weight: 600; margin-right: 10px;}

/* --- VISUELLE SAMMLUNG GALERIE & DASHBOARD --- */
.segmented-control { display: flex; flex-wrap: wrap; justify-content: center; gap: 5px; background: var(--btn-secondary); padding: 6px; border-radius: 12px; width: fit-content; margin-bottom: 40px; border: 1px solid var(--border-color); margin-left: auto; margin-right: auto;}
.segment-btn { padding: 10px 24px; border: none; background: transparent; color: var(--text-muted); font-size: 0.95rem; font-weight: 600; cursor: pointer; border-radius: 8px; transition: all 0.2s; }
.segment-btn.active { background: var(--bg-card); color: var(--text-main); box-shadow: 0 2px 8px var(--shadow-color); }

.dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: start;}
@media (max-width: 900px) { .dashboard-grid { grid-template-columns: 1fr; } }
.top-card-item { display: flex; align-items: center; gap: 15px; padding: 15px 0; border-bottom: 1px solid var(--border-color); }
.top-card-item:last-child { border-bottom: none; }
.top-card-img { width: 50px; border-radius: 4px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }

.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 30px; margin-top: 20px; }
.gallery-item { background: var(--bg-card); border-radius: 16px; padding: 15px; box-shadow: 0 4px 16px var(--shadow-color); text-align: center; transition: transform 0.2s, box-shadow 0.2s; position: relative; border: 1px solid var(--border-color); }
.gallery-item:hover { transform: translateY(-5px); box-shadow: 0 15px 35px var(--shadow-color); }
.gallery-img { width: 100%; border-radius: 4.75% / 3.5%; display: block; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.gallery-price-tag { display: inline-block; background: var(--btn-secondary); color: var(--price-color); font-weight: 600; padding: 6px 12px; border-radius: 8px; font-size: 0.9rem; margin-top: 10px; }
.gallery-remove-btn { position: absolute; top: -10px; right: -10px; background: var(--danger-color); color: white; border: none; width: 28px; height: 28px; border-radius: 50%; font-weight: bold; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(255, 59, 48, 0.4); transition: transform 0.2s, opacity 0.2s; z-index: 10; opacity: 0; }
.gallery-item:hover .gallery-remove-btn { opacity: 1; } 
.gallery-remove-btn:hover { transform: scale(1.1); }

/* --- DECK BUILDER & VISUALIZER --- */
.split-editor-container { display: grid; grid-template-columns: 1fr 1fr; gap: 50px; margin-top: 30px; }
@media (max-width: 1100px) { .split-editor-container { grid-template-columns: 1fr; } }
.deck-textarea { height: 500px; background: var(--input-bg); border: 1px solid var(--border-color); font-family: "SF Mono", Consolas, monospace; font-size: 1.05rem; line-height: 1.6; }
.deck-group-title { border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-top: 30px; margin-bottom: 20px; font-size: 1.4rem;}

.deck-card-wrapper { position: relative; transition: z-index 0.3s; }
.deck-card-wrapper:hover { z-index: 50; }
.deck-card-img { width: 100%; border-radius: 4.75% / 3.5%; display: block; box-shadow: 0 4px 10px rgba(0,0,0,0.1); transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.deck-card-wrapper:hover .deck-card-img { transform: scale(1.5); box-shadow: 0 20px 40px rgba(0,0,0,0.4); }

.card-badge { position: absolute; top: -8px; right: -8px; background: var(--danger-color); color: white; border-radius: 12px; padding: 4px 8px; font-size: 0.85rem; font-weight: 700; box-shadow: 0 4px 8px rgba(0,0,0,0.3); z-index: 5; border: 2px solid var(--bg-card); pointer-events: none;}

/* --- PLAYTESTER (STARTHAND SIMULATOR) --- */
.playtest-hand-container { display: flex; justify-content: center; align-items: center; min-height: 400px; margin-top: 40px; padding: 20px; }
.playtest-card { 
  width: 220px; border-radius: 4.75% / 3.5%; 
  box-shadow: -10px 10px 30px rgba(0,0,0,0.4); 
  margin-left: -130px; 
  transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275), margin 0.3s; 
  position: relative; 
  cursor: grab;
}
.playtest-card:first-child { margin-left: 0; }
.playtest-card:hover { 
  transform: translateY(-40px) scale(1.15); 
  z-index: 100 !important; 
  margin-right: 50px; 
  margin-left: -80px; 
}

/* --- PROXY DRUCK BEREICH --- */
@media print {
  body * { visibility: hidden !important; }
  .proxy-print-area, .proxy-print-area * { visibility: visible !important; }
  .proxy-print-area { 
    position: absolute; left: 0; top: 0; width: 100%; 
    display: grid; 
    grid-template-columns: repeat(3, 63mm); 
    grid-auto-rows: 88mm;
    gap: 0; 
    justify-content: center; 
    padding: 0; margin: 0;
  }
  .proxy-print-img { width: 63mm; height: 88mm; display: block; border: 1px solid #ccc; box-sizing: border-box;}
  .apple-nav-container, .segmented-control, .primary-btn { display: none !important; }
}
.proxy-preview-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 15px; margin-top: 20px; }

/* --- KI JUDGE WIDGET (Mini) --- */
.judge-widget-btn { position: fixed; bottom: 30px; right: 30px; width: 60px; height: 60px; border-radius: 50%; background: var(--accent-color); color: var(--accent-text); border: none; box-shadow: 0 10px 30px var(--shadow-color); cursor: pointer; z-index: 10000; transition: transform 0.2s; display: flex; align-items: center; justify-content: center; }
.judge-widget-btn:hover { transform: scale(1.1); }
.judge-chat-window { position: fixed; bottom: 100px; right: 30px; width: 350px; max-height: 500px; background: var(--bg-card); border-radius: 20px; box-shadow: 0 20px 50px rgba(0,0,0,0.3); border: 1px solid var(--border-color); z-index: 10000; display: flex; flexDirection: column; overflow: hidden; animation: slideUp 0.3s ease; }
@keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
.judge-header { background: var(--accent-color); color: var(--accent-text); padding: 15px 20px; font-weight: 600; font-size: 1.1rem; display: flex; justify-content: space-between; align-items: center;}
.judge-body { padding: 20px; overflow-y: auto; flex-grow: 1; max-height: 350px; font-size: 0.95rem; line-height: 1.5; color: var(--text-main); }
.judge-input-area { display: flex; padding: 15px; border-top: 1px solid var(--border-color); background: var(--bg-main); }
.judge-input-area input { flex-grow: 1; padding: 10px 15px; border-radius: 20px; border: 1px solid var(--border-color); font-size: 0.95rem; margin-right: 10px; background: var(--input-bg); color: var(--text-main); outline: none; }
.judge-input-area button { background: var(--accent-color); color: var(--accent-text); border: none; border-radius: 50%; width: 40px; height: 40px; cursor: pointer; display: flex; align-items: center; justify-content: center; }

.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0, 0, 0, 0.6); backdrop-filter: blur(10px); display: flex; justify-content: center; align-items: center; z-index: 10000; overflow-y: auto;}
.modal-content { background: var(--bg-card); border-radius: 24px; padding: 50px; width: 90%; max-width: 850px; box-shadow: 0 30px 60px rgba(0,0,0,0.3); position: relative; border: 1px solid var(--border-color); margin: 40px auto;}
.close-btn { position: absolute; top: 20px; right: 20px; background: var(--btn-secondary); color: var(--text-main); border: none; width: 36px; height: 36px; border-radius: 50%; cursor: pointer; display: flex; justify-content: center; align-items: center; transition: background 0.2s;}
.close-btn:hover { background: var(--btn-secondary-hover); }
.spinner { border: 3px solid var(--border-color); border-top: 3px solid var(--accent-color); border-radius: 50%; width: 32px; height: 32px; animation: spin 1s linear infinite; margin: 0 auto; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
`;

function App() {
  const [currentUser, setCurrentUser] = useState(localStorage.getItem("username") || null);
  const [userRole, setUserRole] = useState("free");
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isJudgeOpen, setIsJudgeOpen] = useState(false); 
  const navigate = useNavigate();
  const location = useLocation();

  const handleLoginSuccess = (username, token, role) => {
    localStorage.setItem("username", username);
    localStorage.setItem("access_token", token || "");
    setCurrentUser(username);
    setUserRole(role || "free");
  };

  const handleLogout = () => {
    localStorage.removeItem("username");
    localStorage.removeItem("access_token");
    setCurrentUser(null);
    setUserRole("free");
  };

  useEffect(() => {
    if (isDarkMode) document.body.classList.add('dark-mode');
    else document.body.classList.remove('dark-mode');
  }, [isDarkMode]);

  // Load user role when current user changes
  useEffect(() => {
    if (currentUser) {
      fetch(`/api/user/role/${currentUser}`)
        .then(res => res.json())
        .then(data => {
          if (data && data.rolle) {
            setUserRole(data.rolle);
          }
        })
        .catch(() => setUserRole("free"));
    } else {
      setUserRole("free");
    }
  }, [currentUser]);

  // Handle Stripe callback URL parameters
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('status') === 'success') {
      const user = params.get('user') || currentUser;
      const isMock = params.get('mock_upgrade') === 'true';
      
      if (isMock && user) {
        fetch('/api/user/update-role', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ benutzername: user, rolle: 'premium' })
        })
        .then(res => res.json())
        .then(data => {
          if (data && data.erfolg) {
            alert("Upgrade erfolgreich durchgeführt! (Simulation)");
            setUserRole("premium");
            navigate('/premium');
          }
        });
      } else if (params.get('session_id') && user) {
        fetch(`/api/user/role/${user}`)
          .then(res => res.json())
          .then(data => {
            if (data && data.rolle === 'premium') {
              alert("Upgrade erfolgreich durchgeführt! Vielen Dank.");
              setUserRole("premium");
              navigate('/premium');
            } else {
              setTimeout(() => {
                window.location.reload();
              }, 1500);
            }
          });
      }
    }
  }, [location, currentUser, navigate]);

  if (!currentUser) return <><style>{globalStyles}</style><AuthScreen onLoginSuccess={handleLoginSuccess} /></>;
  
  return (
    <>
      <style>{globalStyles}</style>
      <AppleHeader currentUser={currentUser} setCurrentUser={handleLogout} isDarkMode={isDarkMode} setIsDarkMode={setIsDarkMode} setIsJudgeOpen={setIsJudgeOpen} />
      <main>
        <Routes>
          <Route path="/" element={<EntdeckenHub currentUser={currentUser} userRole={userRole} />} />
          <Route path="/sammlung" element={<MeineSammlung currentUser={currentUser} userRole={userRole} setUserRole={setUserRole} />} />
          <Route path="/decks" element={<DecksView currentUser={currentUser} userRole={userRole} />} />
          <Route path="/premium" element={<PremiumPage currentUser={currentUser} userRole={userRole} setUserRole={setUserRole} />} />
        </Routes>
      </main>
      <JudgeWidget open={isJudgeOpen} setOpen={setIsJudgeOpen} currentUser={currentUser} userRole={userRole} />
    </>
  );
}

export default App;