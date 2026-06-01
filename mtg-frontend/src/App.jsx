import { useState, useEffect, useRef } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'

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
  
  --price-color: #248A3D; 
  --danger-color: #FF3B30;
  --danger-bg: rgba(255, 59, 48, 0.1);
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
  
  --price-color: #30D158;
  --danger-color: #FF453A;
  --danger-bg: rgba(255, 69, 58, 0.15);
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

const Icons = {
  Sun: () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>,
  Moon: () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>,
  Chat: () => <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  Send: () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>,
  Cart: () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/></svg>,
  Sparkles: () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>,
  ExternalLink: () => <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
};

const getScryfallImage = (cardName) => {
  if (!cardName) return "";
  return `https://api.scryfall.com/cards/named?exact=${encodeURIComponent(cardName.trim())}&format=image`;
};

function JudgeWidget({ open, setOpen }) {
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState([{role: "judge", text: "Hallo. Ich bin der MTG Judge. Hast du eine Regelfrage zu einer Interaktion?"}]);
  const [loading, setLoading] = useState(false);

  const askJudge = async () => {
    if(!question.trim()) return;
    const userQ = question;
    setChat([...chat, {role: "user", text: userQ}]);
    setQuestion(""); setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/judge`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frage: userQ })
      });
      const data = await res.json();
      setChat(prev => [...prev, {role: "judge", text: data.antwort}]);
    } catch {
      setChat(prev => [...prev, {role: "judge", text: "Verbindungsfehler zum Judge-Netzwerk."}]);
    }
    loading(false);
  };

  return (
    <>
      <button className="judge-widget-btn" onClick={() => setOpen(!open)} title="Regelfragen klären">
        <Icons.Chat />
      </button>
      {open && (
        <div className="judge-chat-window">
          <div className="judge-header">
            <span>KI-Judge</span>
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
            <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && askJudge()} placeholder="Frag den Judge..." />
            <button onClick={askJudge}><Icons.Send /></button>
          </div>
        </div>
      )}
    </>
  )
}

function AppleHeader({ currentUser, setCurrentUser, isDarkMode, setIsDarkMode, setIsJudgeOpen }) {
  const navigate = useNavigate();
  const [hoveredNav, setHoveredNav] = useState(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const timeoutRef = useRef(null);

  const handleMouseEnter = (navItem) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (navItem) {
      setHoveredNav(navItem);
      setIsMenuOpen(true);
    } else {
      setIsMenuOpen(false);
      setHoveredNav(null);
    }
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => {
      setIsMenuOpen(false);
      setHoveredNav(null);
    }, 250); 
  };

  return (
    <nav className={`apple-nav-container ${isMenuOpen ? 'menu-open' : ''}`} onMouseLeave={handleMouseLeave}>
      <ul className="apple-nav-list">
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" style={{fontWeight: 600, fontSize: '1rem', opacity: 1}}>MTG Pro</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('suche')}>
          <span className="apple-nav-link" onClick={() => {navigate('/'); setIsMenuOpen(false); setHoveredNav(null);}}>Suche & KI</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('sammlung')}>
          <span className="apple-nav-link" onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Sammlung</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter('decks')}>
          <span className="apple-nav-link" onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Decks</span>
        </li>
        <li className="apple-nav-item" style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '15px'}} onMouseEnter={() => handleMouseEnter(null)}>
          <button className="theme-toggle" onClick={() => setIsDarkMode(!isDarkMode)} title="Theme wechseln">
            {isDarkMode ? <Icons.Sun /> : <Icons.Moon />}
          </button>
          <span className="apple-nav-link" style={{color: 'var(--text-muted)'}}>{currentUser}</span>
        </li>
        <li className="apple-nav-item" onMouseEnter={() => handleMouseEnter(null)}>
          <span className="apple-nav-link" onClick={() => setCurrentUser(null)}>Abmelden</span>
        </li>
      </ul>

      <div className={`global-mega-menu ${isMenuOpen && hoveredNav ? 'open' : ''}`}>
        <div className="mega-menu-inner">
           <div className={`mega-content-panel ${hoveredNav === 'suche' ? 'active' : ''}`}>
               <div className="dropdown-column">
                   <h4>Entdecken</h4>
                   <a onClick={() => {navigate('/'); setIsMenuOpen(false); setHoveredNav(null);}}>Kartensuche</a>
                   <a onClick={() => {navigate('/?view=trends'); setIsMenuOpen(false); setHoveredNav(null);}}>Beliebte Karten (Trends)</a>
                   <a href="https://www.cardmarket.com/de/Magic" target="_blank" rel="noopener noreferrer" style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                     Marktplatz (Cardmarket) <Icons.ExternalLink />
                   </a>
               </div>
               <div className="dropdown-column">
                   <h4>KI-Assistent</h4>
                   <a onClick={() => {navigate('/?view=synergy'); setIsMenuOpen(false); setHoveredNav(null);}}>Synergie-Analyse</a>
                   <a onClick={() => {navigate('/?view=judge&tab=chat'); setIsMenuOpen(false); setHoveredNav(null);}}>MTG Regel-Judge</a>
                   <a onClick={() => {navigate('/?view=judge&tab=rulebook'); setIsMenuOpen(false); setHoveredNav(null);}}>Offizielles Regelbuch</a>
               </div>
           </div>

           <div className={`mega-content-panel ${hoveredNav === 'sammlung' ? 'active' : ''}`}>
               <div className="dropdown-column">
                   <h4>Portfolio</h4>
                   <a onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Alben Übersicht</a>
                   <a onClick={() => {navigate('/sammlung?tab=alben'); setIsMenuOpen(false); setHoveredNav(null);}}>Neues Album anlegen</a>
                   <a onClick={() => {navigate('/sammlung?tab=dashboard'); setIsMenuOpen(false); setHoveredNav(null);}}>Marktwert & Finanzen</a>
               </div>
               <div className="dropdown-column">
                   <h4>Organisation</h4>
                   <a onClick={() => {navigate('/sammlung?tab=wishlist'); setIsMenuOpen(false); setHoveredNav(null);}}>Wunschliste (Wishlist)</a>
                   <a onClick={() => {navigate('/sammlung?tab=import'); setIsMenuOpen(false); setHoveredNav(null);}}>Massen-Import (CSV)</a>
                   <a onClick={() => {navigate('/sammlung?tab=export'); setIsMenuOpen(false); setHoveredNav(null);}}>Sammlung exportieren</a>
               </div>
           </div>

           <div className={`mega-content-panel ${hoveredNav === 'decks' ? 'active' : ''}`}>
               <div className="dropdown-column">
                   <h4>Deck-Management</h4>
                   <a onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Deck-Center</a>
                   <a onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Neues Deck erstellen</a>
               </div>
               <div className="dropdown-column">
                   <h4>Analyse & Tools</h4>
                   <a onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Visueller Builder & Starthand</a>
                   <a onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Stats & Analyse</a>
               </div>
               <div className="dropdown-column">
                   <h4>Export</h4>
                   <a onClick={() => {navigate('/decks'); setIsMenuOpen(false); setHoveredNav(null);}}>Proxy-Druck (PDF)</a>
               </div>
           </div>
        </div>
      </div>
    </nav>
  );
}

function AuthScreen({ onLoginSuccess }) {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    const endpoint = isRegister ? "/api/register" : "/api/login";
    try {
      const res = await fetch(`http://localhost:8000${endpoint}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ benutzername: username, passwort: password })
      });
      const data = await res.json();
      if (data.erfolg) {
        if (isRegister) { setMessage("Konto erstellt. Bitte einloggen."); setIsRegister(false); setPassword(""); } 
        else { onLoginSuccess(username); }
      } else { setMessage(data.error); }
    } catch { setMessage("Serverfehler."); }
  };

  return (
    <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: 'var(--bg-main)'}}>
      <div className="content-card" style={{maxWidth: '450px', width: '100%', textAlign: 'center', padding: '60px'}}>
        <h2 style={{fontSize: '2.5rem'}}>MTG Pro</h2>
        <p style={{marginBottom: '40px'}}>{isRegister ? "Erstelle dein Konto." : "Melde dich bei MTG Pro an."}</p>
        {message && <p style={{color: '#FF3B30'}}>{message}</p>}
        <form onSubmit={handleSubmit} style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
          <input type="text" placeholder="Benutzername" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input type="password" placeholder="Passwort" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="submit" className="primary-btn" style={{marginTop: '10px', width: '100%'}}>Weiter</button>
        </form>
        <p style={{marginTop: '40px', fontSize: '0.95rem'}}><span onClick={() => { setIsRegister(!isRegister); setMessage(""); }} style={{cursor: 'pointer', color: 'var(--text-muted)', fontWeight: 600}}>{isRegister ? "Bereits registriert? Anmelden" : "Konto erstellen"}</span></p>
      </div>
    </div>
  );
}

function SynergieAnsicht({ currentUser }) {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const initialCard = queryParams.get('card');

  const [activeMode, setActiveMode] = useState('single'); 
  const [suche, setSuche] = useState("");
  const [karte, setKarte] = useState(null);
  const [combos, setCombos] = useState([]);
  const [laedt, setLaedt] = useState(false);
  
  const [userDecks, setUserDecks] = useState([]);
  const [userAlbums, setUserAlbums] = useState({});
  const [selectedTarget, setSelectedTarget] = useState("");

  const topTournamentCombos = [
    { format: "cEDH / Legacy", name: "Thassa's Oracle + Demonic Consultation", cards: ["Thassa's Oracle", "Demonic Consultation"], grund: "Exiliere deine gesamte Bibliothek für 1 schwarzes Mana und gewinne das Spiel auf der Stelle durch den ETB-Trigger von Thassa's Oracle." },
    { format: "Modern / Pioneer", name: "Kiki-Jiki, Mirror Breaker + Zealous Conscripts", cards: ["Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"], grund: "Erzeuge unendlich viele Eile-Kopien von Zealous Conscripts, die bei ihrem ETB wiederum Kiki-Jiki enttappen. Infinite Damage." },
    { format: "Modern", name: "Grief + Ephemerate", cards: ["Grief", "Ephemerate"], grund: "Zerstöre die Hand deines Gegners in Zug 1 durch Evoke und sofortiges Blink-Modul, sodass die Kreatur ohne Opfer-Nachteil dauerhaft im Spiel bleibt." },
    { format: "cEDH / Vintage", name: "Underworld Breach + Brain Freeze + Lion's Eye Diamond", cards: ["Underworld Breach", "Brain Freeze", "Lion's Eye Diamond"], grund: "Mühle dein gesamtes Deck in den Friedhof und generiere nebenbei unendlich viel Storm-Count und rotes Mana." }
  ];

  useEffect(() => {
    if(initialCard && !karte && !laedt && activeMode === 'single') {
      setSuche(initialCard);
      analysiereSynergien(initialCard);
    }
  }, [initialCard, activeMode]);

  useEffect(() => {
    if (activeMode === 'decks') {
        fetch(`http://localhost:8000/api/decks/${currentUser}`).then(r => r.json()).then(data => {
            if(Array.isArray(data)) { setUserDecks(data); if(data.length > 0) setSelectedTarget(data[0].id.toString()); }
        }).catch(e => console.log(e));
    } else if (activeMode === 'albums') {
        fetch(`http://localhost:8000/api/sammlung/${currentUser}`).then(r => r.json()).then(data => {
            if(data && data.erfolg && data.alben) { setUserAlbums(data.alben); const keys = Object.keys(data.alben); if(keys.length > 0) setSelectedTarget(keys[0]); }
        }).catch(e => console.log(e));
    }
  }, [activeMode, currentUser]);

  const handleSearchSubmit = () => { if(!suche) return; analysiereSynergien(suche); }

  const analysiereSynergien = async (searchTerm) => {
    setKarte(null); setCombos([]); setLaedt(true);
    try {
      const resImg = await fetch(`http://localhost:8000/api/suche/${searchTerm}`);
      if (!resImg.ok) throw new Error();
      const dataImg = await resImg.json();
      if (!dataImg.error) setKarte(dataImg);
      const resCombos = await fetch(`http://localhost:8000/api/combos/${dataImg.name || searchTerm}`);
      const dataCombos = await resCombos.json();
      const empf = Array.isArray(dataCombos.empfehlungen) ? dataCombos.empfehlungen : [];
      const normalizedCombos = empf.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar." }));
      setCombos(normalizedCombos);
    } catch { alert("Analyse fehlgeschlagen."); }
    setLaedt(false);
  }

  const runScanner = async () => {
      if(!selectedTarget) return;
      setLaedt(true); setCombos([]);
      let listeFürKI = "";
      if (activeMode === 'decks') {
          const deck = userDecks.find(d => d.id.toString() === selectedTarget);
          if (deck) listeFürKI = deck.liste || "";
      } else if (activeMode === 'albums') {
          const kartenImAlbum = Array.isArray(userAlbums[selectedTarget]) ? userAlbums[selectedTarget] : [];
          listeFürKI = kartenImAlbum.map(k => k?.name || "").join('\n');
      }

      if(!listeFürKI.trim()) { alert("Das ausgewählte Ziel ist leer."); setLaedt(false); return; }

      try {
          const res = await fetch(`http://localhost:8000/api/scan_combos`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ karten_liste: listeFürKI }) });
          const data = await res.json();
          if (data && data.error) { alert("KI Meldung: " + data.error); setLaedt(false); return; }

          let normalizedCombos = [];
          if (Array.isArray(data)) {
              normalizedCombos = data.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar." }));
          } else if (data && data.combos && Array.isArray(data.combos)) {
              normalizedCombos = data.combos.map(c => ({ name: c?.name || c?.karten || c?.combo || "Unbekannte Combo", grund: c?.grund || c?.erklaerung || c?.beschreibung || "Keine Erklärung verfügbar." }));
          }
          setCombos(normalizedCombos);
      } catch { alert("Fehler beim Scannen der Sammlung. Bitte API checken."); }
      setLaedt(false);
  };

  const parseComboCards = (comboString) => {
    if (!comboString || typeof comboString !== 'string') return [];
    let cleanedString = comboString.replace(/combo|synergy|synergie/gi, "");
    return cleanedString.split(/\+|und|and|&|,|\/|\|/i).map(s => s.trim()).filter(s => s.length > 2);
  }

  return (
    <div className="apple-main-container">
      <div className="search-hero">
        <h2>Synergie-Analyse.</h2>
        <p>Entdecke Combos für Einzelkarten oder lasse die KI deine Decks und Alben nach verborgenen Synergien scannen.</p>
        <div className="segmented-control" style={{marginBottom: '30px', margin: '0 auto 30px auto', display: 'flex'}}>
            <button className={`segment-btn ${activeMode === 'single' ? 'active' : ''}`} onClick={() => {setActiveMode('single'); setCombos([]); setKarte(null);}}>Einzelkarte</button>
            <button className={`segment-btn ${activeMode === 'decks' ? 'active' : ''}`} onClick={() => {setActiveMode('decks'); setCombos([]); setKarte(null);}}>Meine Decks scannen</button>
            <button className={`segment-btn ${activeMode === 'albums' ? 'active' : ''}`} onClick={() => {setActiveMode('albums'); setCombos([]); setKarte(null);}}>Alben scannen</button>
        </div>
        {activeMode === 'single' && (
            <div className="search-bar-wrapper">
                <input value={suche} onChange={(e) => setSuche(e.target.value)} placeholder="Kartennamen eingeben..." onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()} style={{boxShadow: '0 8px 20px var(--shadow-color)'}} />
                <button className="primary-btn" onClick={handleSearchSubmit}>{laedt ? "Analysiere..." : "Analysieren"}</button>
            </div>
        )}
        {activeMode === 'decks' && (
            <div className="search-bar-wrapper">
                <select value={selectedTarget} onChange={e => setSelectedTarget(e.target.value)} style={{boxShadow: '0 8px 20px var(--shadow-color)', background: 'var(--input-bg)', border: '1px solid var(--border-color)'}}>
                    <option value="" disabled>Bitte Deck auswählen...</option>
                    {userDecks.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <button className="primary-btn" onClick={runScanner}>{laedt ? "Scanne..." : "Scannen"}</button>
            </div>
        )}
        {activeMode === 'albums' && (
            <div className="search-bar-wrapper">
                <select value={selectedTarget} onChange={e => setSelectedTarget(e.target.value)} style={{boxShadow: '0 8px 20px var(--shadow-color)', background: 'var(--input-bg)', border: '1px solid var(--border-color)'}}>
                    <option value="" disabled>Bitte Album auswählen...</option>
                    {Object.keys(userAlbums || {}).map(a => <option key={a} value={a}>{a}</option>)}
                </select>
                <button className="primary-btn" onClick={runScanner}>{laedt ? "Scanne..." : "Scannen"}</button>
            </div>
        )}
      </div>

      {laedt && <div style={{textAlign: 'center', marginTop: '60px'}}><div className="spinner"></div><p style={{marginTop: '20px', color: 'var(--text-muted)'}}>{activeMode === 'single' ? "KI ermittelt beste Kombinationen..." : "Durchsuche Datenbank nach verborgenen Synergien... (Das kann kurz dauern)"}</p></div>}

      {activeMode === 'single' && !karte && !laedt && (
        <div className="content-card" style={{padding: '40px'}}>
          <h3 style={{fontSize: '1.8rem', marginBottom: '30px'}}>Meta-Breaker: Top Turnier-Combos</h3>
          <div className="dashboard-grid">
            {(topTournamentCombos || []).map((combo, index) => (
              <div key={index} className="tournament-combo-card">
                <span className="combo-badge">{combo.format}</span>
                <div className="combo-images-container">
                  {(combo.cards || []).map((cardName, idx) => (
                    <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                  ))}
                </div>
                <h4 style={{fontSize: '1.3rem', color: 'var(--text-main)', marginBottom: '15px'}}>{combo.name}</h4>
                <p style={{margin: 0, color: 'var(--text-muted)'}}>{combo.grund}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeMode === 'single' && karte && !laedt && (
        <div className="content-card">
          <div className="result-layout" style={{gridTemplateColumns: '350px 1fr'}}>
            <div className="card-image-wrapper">
              <img src={karte?.prints?.[0]?.bild_url || "https://via.placeholder.com/180"} alt={karte?.name || "Unbekannt"} className="main-card-img" style={{maxWidth: '350px'}} />
              <h3 style={{marginTop: '20px', fontSize: '1.5rem'}}>{karte?.name}</h3>
              <p style={{margin: 0}}>{karte?.typ}</p>
            </div>
            <div>
              <h3 style={{fontSize: '2rem', marginBottom: '30px'}}>KI-Gefundene Combos</h3>
              {(!combos || combos.length === 0) ? <p>Keine spezifischen Combos gefunden.</p> : combos.map((c, i) => {
                if (!c) return null;
                const comboCardNames = parseComboCards(c.name);
                return (
                  <div key={i} className="synergy-combo-card">
                    {comboCardNames.length > 0 && (
                      <div className="combo-images-container">
                        {comboCardNames.map((cardName, idx) => (
                          <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                        ))}
                      </div>
                    )}
                    <h4 style={{margin: 0, color: 'var(--text-main)', fontSize: '1.3rem', marginBottom: '10px'}}>{c.name}</h4>
                    <p style={{margin: 0, fontSize: '1.05rem', color: 'var(--text-muted)'}}>{c.grund}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {(activeMode === 'decks' || activeMode === 'albums') && !laedt && combos && combos.length > 0 && (
          <div className="content-card" style={{padding: '40px'}}>
              <h3 style={{fontSize: '2rem', marginBottom: '30px'}}>Gefundene Synergien & Combos</h3>
              {combos.map((c, i) => {
                if(!c) return null;
                const comboCardNames = parseComboCards(c.name);
                return (
                  <div key={i} className="synergy-combo-card">
                    {comboCardNames.length > 0 && (
                      <div className="combo-images-container">
                        {comboCardNames.map((cardName, idx) => (
                          <img key={idx} src={getScryfallImage(cardName)} alt={cardName} className="combo-card-img" onError={(e) => e.target.style.display = 'none'} />
                        ))}
                      </div>
                    )}
                    <h4 style={{margin: 0, color: 'var(--text-main)', fontSize: '1.3rem', marginBottom: '10px'}}>{c.name}</h4>
                    <p style={{margin: 0, fontSize: '1.05rem', color: 'var(--text-muted)'}}>{c.grund}</p>
                  </div>
                );
              })}
          </div>
      )}

      {(activeMode === 'decks' || activeMode === 'albums') && !laedt && (!combos || combos.length === 0) && selectedTarget && (
          <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Klicke auf Scannen, um verborgene Combos zu finden, oder wähle ein anderes Ziel.</p>
      )}

    </div>
  );
}

function JudgeAnsicht() {
  const location = useLocation();
  const queryParams = new URLSearchParams(location.search);
  const initialTab = queryParams.get('tab') || 'chat';
  const [activeTab, setActiveTab] = useState(initialTab);
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState([{role: "judge", text: "Willkommen im offiziellen Judge-Center. Bitte beschreibe die Spielsituation oder Regelfrage so genau wie möglich."}]);
  const [loading, setLoading] = useState(false);
  const [ruleSearch, setRuleSearch] = useState("");
  
  const rulesDatabase = [
    { id: "101.1.", title: "Die Goldene Regel (The Golden Rule)", text: "Wann immer der Text einer Karte einer Regel widerspricht, hat der Text der Karte Vorrang. Die Karte modifiziert die Regel für diese specific Situation." },
    { id: "117.1.", title: "Priorität (Priority)", text: "Spieler können Zaubersprüche und Fähigkeiten nur wirken oder aktivieren, wenn sie Priorität haben. Ein Spieler erhält Priorität, nachdem ein Zauberspruch oder eine Fähigkeit verrechnet wurde, oder zu Beginn jedes Segments/jeder Phase (außer Untap und Cleanup)." },
    { id: "117.3c", title: "Priorität abgeben", text: "Wenn ein Spieler Priorität hat und nichts tun möchte, gibt er die Priorität ab. Wenn alle Spieler nacheinander Priorität abgeben, wird das oberste Objekt auf dem Stapel verrechnet. Ist der Stapel leer, endet das Segment/die Phase." },
    { id: "400.7.", title: "Zonenwechsel (Zone Changes)", text: "Ein Objekt, das von einer Zone in eine andere wechselt, wird zu einem völlig neuen Objekt. Es hat keine Erinnerung an seine vorherige Existenz in der alten Zone." },
    { id: "506.1.", title: "Die Kampfphase (Combat Phase)", text: "Die Kampfphase besteht aus fünf Segmenten, in dieser Reihenfolge: Beginn des Kampfes, Angreifer deklarieren, Blocker deklarieren, Kampfschaden und Ende des Kampfes." },
    { id: "509.1.", title: "Angreifer deklarieren", text: "Der aktive Spieler wählt, welche seiner Kreaturen angreifen. Das Tappen dieser Kreaturen ist Teil der Deklaration. Danach erhalten Spieler Priorität, um Spontanzauber zu wirken." },
    { id: "509.2.", title: "Blocker deklarieren", text: "Der verteidigende Spieler wählt, welche Kreaturen er zum Blocken einsetzt. Wird ein Angreifer geblockt, bleibt er für den Rest des Kampfes 'geblockt', selbst wenn der Blocker das Spiel verlässt." },
    { id: "608.2b", title: "Verrechnung von Sprüchen (Targets)", text: "Wenn ein Zauberspruch oder eine Fähigkeit Ziele (Targets) benötigt, wird bei der Verrechnung geprüft, ob sie noch legal sind. Sind alle Ziele illegal geworden, verpufft der Spruch ergebnislos ('fizzles')." },
    { id: "702.8.", title: "Todesberührung (Deathtouch)", text: "Jeder Schaden ungleich null, der von einer Quelle mit Todesberührung einer Kreatur zugefügt wird, ist tödlicher Schaden, ungeachtet der Widerstandskraft der Kreatur." },
    { id: "702.10.", title: "Doppelschlag (Double Strike)", text: "Kreaturen mit Doppelschlag fügen ihren Kampfschaden in einem zusätzlichen, vorgezogenen Kampfschadens-Segment zu (gleichzeitig mit Erstschlag), und dann noch einmal im regulären Kampfschadens-Segment." },
    { id: "702.12.", title: "Trampelschaden (Trample)", text: "Überschüssiger Kampfschaden einer angreifenden Kreatur mit Trampelschaden, der nicht benötigt wird, um alle ihre Blocker tödlich zu verletzen, kann stattdessen dem verteidigenden Spieler oder Planeswalker zugefügt werden." },
    { id: "702.14.", title: "Fluchsicher (Hexproof)", text: "Ein Permanent oder Spieler mit Fluchsicher kann nicht das Ziel von Zaubersprüchen oder Fähigkeiten sein, die von einem Gegner kontrolliert werden." },
    { id: "702.16.", title: "Unzerstörbar (Indestructible)", text: "Kreaturen mit Unzerstörbar können nicht durch 'Zerstöre'-Effekte (Destroy) oder tödlichen Schaden auf den Friedhof gelegt werden. Sie können aber ins Exil geschickt (Exile) oder geopfert (Sacrifice) werden." },
    { id: "704.5f", title: "State-Based Actions (Toughness 0)", text: "Wenn die Widerstandskraft (Toughness) einer Kreatur 0 oder weniger beträgt, wird sie auf den Friedhof ihres Besitzers gelegt. Dies ist kein 'Zerstören' und umgeht Unzerstörbar." }
  ];

  const filteredRules = rulesDatabase.filter(r => 
    r.title.toLowerCase().includes(ruleSearch.toLowerCase()) || 
    r.text.toLowerCase().includes(ruleSearch.toLowerCase()) ||
    r.id.includes(ruleSearch)
  );

  const askJudge = async () => {
    if(!question.trim()) return;
    const userQ = question;
    setChat([...chat, {role: "user", text: userQ}]);
    setQuestion(""); setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/judge`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frage: userQ })
      });
      const data = await res.json();
      setChat(prev => [...prev, {role: "judge", text: data.antwort}]);
    } catch {
      setChat(prev => [...prev, {role: "judge", text: "Verbindungsfehler."}]);
    }
    setLoading(false);
  };

  return (
    <div className="apple-main-container" style={{maxWidth: '1000px'}}>
      <div className="search-hero" style={{paddingBottom: '20px'}}>
        <h2>MTG Regel-Judge.</h2>
        <p>Dein KI-Schiedsrichter für Spielsituationen und das Handbuch für komplexe Mechaniken.</p>
      </div>

      <div className="segmented-control" style={{marginBottom: '30px', margin: '0 auto', display: 'flex'}}>
        <button className={`segment-btn ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>KI-Chat</button>
        <button className={`segment-btn ${activeTab === 'rulebook' ? 'active' : ''}`} onClick={() => setActiveTab('rulebook')}>Offizielles Regelbuch</button>
      </div>

      {activeTab === 'chat' && (
        <div className="judge-full-container">
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
            <input value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => e.key === 'Enter' && askJudge()} placeholder="Wie löst sich dieser Effekt auf...?" />
            <button className="primary-btn" style={{borderRadius: '980px', padding: '0 30px'}} onClick={askJudge}>Fragen</button>
          </div>
        </div>
      )}

      {activeTab === 'rulebook' && (
        <div className="content-card" style={{padding: '40px'}}>
          <input 
            type="text" 
            placeholder="Regelbuch durchsuchen (z.B. 'Kampfphase', 'Trampelschaden', '702.1')..." 
            value={ruleSearch} 
            onChange={(e) => setRuleSearch(e.target.value)} 
            style={{marginBottom: '30px', background: 'var(--btn-secondary)', border: 'none', boxShadow: 'none'}}
          />
          <div>
            {filteredRules.length === 0 ? <p>Keine passende Regel gefunden.</p> : filteredRules.map((rule, i) => (
              <div key={i} className="rule-card">
                <h4><span className="rule-id">{rule.id}</span> {rule.title}</h4>
                <p>{rule.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function KartenSuche({ currentUser }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const viewMode = queryParams.get('view') || 'search';

  const [karte, setKarte] = useState(null);
  const [suche, setSuche] = useState("");
  const [laedt, setLaedt] = useState(false);
  const [selectedPrintIndex, setSelectedPrintIndex] = useState(0);
  const [existingAlben, setExistingAlben] = useState([]);
  const [albumMode, setAlbumMode] = useState("select");
  const [albumName, setAlbumName] = useState("");
  const [trendingCards, setTrendingCards] = useState([]);
  const [loadingTrends, setLoadingTrends] = useState(false);

  const isTrendsView = viewMode === 'trends';

  useEffect(() => {
    fetch(`http://localhost:8000/api/sammlung/${currentUser}`).then(res => res.json()).then(data => {
        if(data && data.erfolg && data.alben) {
          const keys = Object.keys(data.alben);
          setExistingAlben(keys);
          if(keys.length > 0) { setAlbumMode("select"); setAlbumName(keys[0]); } else { setAlbumMode("new"); }
        }
      }).catch(e => console.log(e));
  }, [currentUser]);

  useEffect(() => {
      if (isTrendsView && trendingCards.length === 0) loadTrends();
      if (!isTrendsView && suche === "") setKarte(null);
  }, [isTrendsView]);

  if (viewMode === 'synergy') return <SynergieAnsicht currentUser={currentUser} />;
  if (viewMode === 'judge') return <JudgeAnsicht />;

  const loadTrends = async () => {
      setLoadingTrends(true);
      const identifiers = [
          {name: "The One Ring"}, {name: "Sheoldred, the Apocalypse"},
          {name: "Dockside Extortionist"}, {name: "Rhystic Study"},
          {name: "Smothering Tithe"}, {name: "Cyclonic Rift"},
          {name: "Mana Crypt"}, {name: "Fierce Guardianship"}
      ];
      try {
          const res = await fetch("https://api.scryfall.com/cards/collection", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ identifiers })
          });
          const data = await res.json();
          if(data && Array.isArray(data.data)) setTrendingCards(data.data);
      } catch (e) {}
      setLoadingTrends(false);
  };

  const handleSearchSubmit = () => {
    if(!suche) return;
    if(isTrendsView) navigate('/');
    triggerSearch(suche);
  }

  const triggerSearch = async (searchTerm) => {
    setKarte(null); setLaedt(true);
    try {
      const res = await fetch(`http://localhost:8000/api/suche/${searchTerm}`)
      if (!res.ok) { alert("Fehler bei der Serververbindung."); setLaedt(false); return; }
      const data = await res.json()
      if (data.error) alert("Karte nicht gefunden."); 
      else { setKarte(data); setSelectedPrintIndex(0); setSuche(data.name); }
    } catch { alert("Suche fehlgeschlagen."); }
    setLaedt(false);
  }

  const navigateToSynergy = () => {
    if(karte && karte.name) {
        navigate(`/?view=synergy&card=${encodeURIComponent(karte.name)}`);
    }
  }

  const speichereKarte = async () => {
    const finalAlbumName = albumName.trim();
    if(!finalAlbumName) return alert("Bitte Albumnamen eingeben.");
    const actP = karte?.prints?.[selectedPrintIndex];
    if(!actP) return alert("Fehler beim Speichern der Karte.");
    try {
      const res = await fetch(`http://localhost:8000/api/sammlung/hinzufuegen`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ benutzername: currentUser, karten_name: karte.name, album_name: finalAlbumName, bild_url: actP.bild_url || "", preis: actP.preis && actP.preis !== "N/A" ? String(actP.preis) : "0.00" })
      });
      const data = await res.json();
      if (data && data.erfolg) { 
        alert(`Gespeichert in "${finalAlbumName}"!`); 
        if(!existingAlben.includes(finalAlbumName)) setExistingAlben([...existingAlben, finalAlbumName]);
        setAlbumMode("select");
      } 
    } catch { alert("Fehler."); }
  }

  const clickTrendingCard = (cardName) => {
      setSuche(cardName);
      navigate('/');
      triggerSearch(cardName);
  }

  const actPrint = karte && Array.isArray(karte.prints) ? karte.prints[selectedPrintIndex] : null;
  const getCardmarketUrl = (kartenName) => `https://www.cardmarket.com/de/Magic/Products/Search?searchString=${encodeURIComponent(kartenName || "")}`;

  return (
    <div className="apple-main-container">
      <div className="search-hero">
        <h2>{isTrendsView ? 'Markt-Trends.' : 'Intelligente Kartensuche.'}</h2>
        <p>{isTrendsView ? 'Die aktuell gefragtesten Karten im Format.' : 'Finde Versionen, deutsche Übersetzungen und aktuelle Marktdaten.'}</p>
        <div className="search-bar-wrapper">
            <input 
              id="main-search-input"
              value={suche} 
              onChange={(e) => setSuche(e.target.value)} 
              placeholder="Kartennamen eingeben (z.B. Sol Ring)..." 
              onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()} 
              style={{boxShadow: '0 8px 20px var(--shadow-color)'}} 
            />
            <button className="primary-btn" onClick={handleSearchSubmit}>{laedt && !karte ? "Suche..." : "Suchen"}</button>
        </div>
      </div>
      
      {isTrendsView && (
          <div className="content-card">
              <h3 style={{marginBottom: '20px', fontSize: '1.8rem'}}>Top Staples der Woche</h3>
              {loadingTrends ? <div className="spinner"></div> : (
                  <div className="trending-grid">
                      {(trendingCards || []).map(c => (
                          <div key={c?.id || Math.random()} className="trending-item" onClick={() => clickTrendingCard(c?.name)}>
                              <img src={c?.image_uris?.normal || "https://via.placeholder.com/180"} alt={c?.name || "Karte"} />
                              <div className="trending-overlay">
                                  <span>Karte suchen</span>
                              </div>
                          </div>
                      ))}
                  </div>
              )}
          </div>
      )}

      {!isTrendsView && karte && actPrint && (
        <div className="content-card">
          <div className="result-layout">
            <div className="card-image-wrapper">
              <img src={actPrint.bild_url || "https://via.placeholder.com/180"} alt={karte?.name || "Unbekannt"} className="main-card-img" />
              {karte.prints && karte.prints.length > 1 && (
                <div>
                  <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600}}>Alle Editionen</span>
                  <div className="prints-scroll" style={{marginTop: '10px'}}>
                    {karte.prints.map((p, i) => (
                      <img key={i} src={p?.bild_url || "https://via.placeholder.com/180"} className={`print-thumb ${i === selectedPrintIndex ? 'active' : ''}`} onClick={() => setSelectedPrintIndex(i)} title={p?.set_name} alt="Edition" />
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div>
              <div className="info-header">
                <h3>{karte?.name}</h3>
                <p>{karte?.typ} • <strong style={{color: 'var(--text-main)'}}>{actPrint?.set_name}</strong></p>
              </div>
              <div className="translation-box">
                <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '12px'}}>Deutsche Übersetzung (KI)</span>
                <p style={{color: 'var(--text-main)', fontSize: '1.15rem', margin: 0, fontStyle: 'italic'}}>{karte?.text_de}</p>
              </div>
              
              <div style={{display: 'flex', alignItems: 'center', gap: '25px', marginBottom: '40px', flexWrap: 'wrap'}}>
                <div>
                  <span style={{fontSize: '0.95rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'block'}}>Marktwert</span>
                  <p className="price-display">{actPrint?.preis || "0.00"} €</p>
                </div>
                <a href={getCardmarketUrl(karte?.name)} target="_blank" rel="noopener noreferrer" className="market-btn" style={{marginTop: '15px'}}>
                   <Icons.Cart /> Auf Cardmarket kaufen
                </a>
              </div>
              
              <div style={{borderTop: '1px solid var(--border-color)', paddingTop: '30px'}}>
                <button id="synergy-btn" className="secondary-btn" style={{marginBottom: '30px', width: '100%', padding: '18px', fontSize: '1.1rem'}} onClick={navigateToSynergy}>
                   <Icons.Sparkles /> KI-Synergien analysieren
                </button>
                <div style={{display: 'flex', gap: '15px', alignItems: 'center', background: 'var(--btn-secondary)', padding: '20px', borderRadius: '20px'}}>
                  {existingAlben && existingAlben.length > 0 && albumMode === "select" ? (
                    <select value={albumName} onChange={e => { if(e.target.value === "NEW") { setAlbumMode("new"); setAlbumName(""); } else setAlbumName(e.target.value); }} style={{padding: '14px', flexGrow: 1, border: 'none', background: 'var(--input-bg)'}}>
                      {(existingAlben || []).map(a => <option key={a} value={a}>{a}</option>)}
                      <option value="NEW">+ Neues Album erstellen...</option>
                    </select>
                  ) : (
                    <input type="text" placeholder="Neues Album benennen..." value={albumName} onChange={e => setAlbumName(e.target.value)} style={{padding: '14px', flexGrow: 1, border: 'none', background: 'var(--input-bg)'}} />
                  )}
                  <button className="primary-btn" style={{padding: '14px 35px'}} onClick={speichereKarte}>Sichern</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MeineSammlung({ currentUser }) {
  const location = useLocation();
  const navigate = useNavigate();
  const currentTab = new URLSearchParams(location.search).get('tab') || 'alben';

  const [alben, setAlben] = useState({});
  const [newAlbumName, setNewAlbumName] = useState("");
  const [updatingPrices, setUpdatingPrices] = useState(false);
  const [sortOrders, setSortOrders] = useState({});
  
  const [wishlistSearch, setWishlistSearch] = useState("");
  const [isWishlistAdding, setIsWishlistAdding] = useState(false);

  const [importText, setImportText] = useState("");
  const [importAlbum, setImportAlbum] = useState("select");
  const [newImportAlbumName, setNewImportAlbumName] = useState("");
  const [isImporting, setIsImporting] = useState(false);

  const fetchLivePrices = async (albenData) => {
    if (!albenData) return;
    const uniqueNames = new Set();
    Object.values(albenData).forEach(album => {
        if(Array.isArray(album)) album.forEach(k => { if(k && k.name) uniqueNames.add(k.name); });
    });
    const namesArray = Array.from(uniqueNames);
    if (namesArray.length === 0) return;
    
    setUpdatingPrices(true);
    const priceMap = {};
    for (let i = 0; i < namesArray.length; i += 75) {
      const chunk = namesArray.slice(i, i + 75);
      const identifiers = chunk.map(name => ({ name: name }));
      try {
        const res = await fetch("https://api.scryfall.com/cards/collection", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ identifiers }) });
        if(res.ok) {
          const data = await res.json();
          if(data && Array.isArray(data.data)) {
              data.data.forEach(card => { if (card && card.prices && card.prices.eur) priceMap[card.name] = card.prices.eur; });
          }
        }
      } catch (e) {}
    }
    const newAlben = {};
    for (const [albumName, karten] of Object.entries(albenData)) {
      if(Array.isArray(karten)) {
          newAlben[albumName] = karten.filter(k => k != null).map(k => ({ ...k, livePreis: priceMap[k.name] || k.preis || "0.00" }));
      }
    }
    setAlben(newAlben);
    setUpdatingPrices(false);
  };

  const ladeSammlung = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/sammlung/${currentUser}`);
      if (res.ok) {
        const data = await res.json();
        if(data && data.erfolg && data.alben) {
          const cleanedAlben = {};
          for (const [albumName, karten] of Object.entries(data.alben)) {
              if(Array.isArray(karten)) {
                  cleanedAlben[albumName] = karten.filter(k => k && k.name !== "__PLACEHOLDER__");
              }
          }
          setAlben(cleanedAlben);
          fetchLivePrices(cleanedAlben);
        }
      }
    } catch {}
  }

  const erstelleLeeresAlbum = async () => {
    if(!newAlbumName.trim()) return;
    try {
      await fetch(`http://localhost:8000/api/sammlung/hinzufuegen`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ benutzername: currentUser, karten_name: "__PLACEHOLDER__", album_name: newAlbumName.trim(), bild_url: "", preis: "0.00" }) });
      setNewAlbumName(""); ladeSammlung();
    } catch {}
  }

  const loescheKarte = async (karten_id) => {
    await fetch(`http://localhost:8000/api/sammlung/loeschen`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ karten_id }) });
    ladeSammlung();
  }

  const loescheGanzesAlbum = async (albumName) => {
    if(!window.confirm(`Möchtest du das Album "${albumName}" wirklich löschen?`)) return;
    try {
      await fetch(`http://localhost:8000/api/sammlung/album_loeschen`, { 
        method: "POST", headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify({ benutzername: currentUser, album_name: albumName }) 
      });
      ladeSammlung();
    } catch {}
  }

  useEffect(() => { ladeSammlung(); }, []);

  const wishlistKarten = Array.isArray(alben["Wunschliste"]) ? alben["Wunschliste"] : [];
  const portfolioAlben = { ...alben };
  delete portfolioAlben["Wunschliste"];

  const getPriceVal = (k) => {
      if(!k) return 0;
      return parseFloat(String(k.livePreis || k.preis || "0").replace(',', '.')) || 0;
  }
  
  const berechneAlbumWert = (karten) => {
      if(!karten || !Array.isArray(karten)) return "0.00";
      return karten.reduce((summe, karte) => summe + getPriceVal(karte), 0).toFixed(2);
  }
  
  const totalPortfolioWert = Object.values(portfolioAlben).reduce((acc, karten) => {
      if(!Array.isArray(karten)) return acc;
      return acc + parseFloat(berechneAlbumWert(karten))
  }, 0).toFixed(2);
  
  const totalWishlistWert = berechneAlbumWert(wishlistKarten);

  const getAllCardsFlat = () => {
    const all = [];
    Object.entries(portfolioAlben).forEach(([albumName, karten]) => {
      if(Array.isArray(karten)) {
          karten.forEach(k => { if(k) all.push({...k, albumName}) });
      }
    });
    return all;
  };

  const sortiereKarten = (karten, methode) => {
    if(!karten || !Array.isArray(karten)) return [];
    const arr = [...karten].filter(k => k != null);
    if(methode === "priceDesc") return arr.sort((a,b) => getPriceVal(b) - getPriceVal(a));
    if(methode === "priceAsc") return arr.sort((a,b) => getPriceVal(a) - getPriceVal(b));
    if(methode === "az") return arr.sort((a,b) => (a?.name || "").localeCompare(b?.name || ""));
    return arr; 
  };

  const addToWishlist = async () => {
    if(!wishlistSearch) return;
    setIsWishlistAdding(true);
    try {
        const res = await fetch(`http://localhost:8000/api/suche/${wishlistSearch}`);
        const data = await res.json();
        if(data && data.error) {
            alert("Karte nicht gefunden. Bitte Namen prüfen.");
        } else if (data && Array.isArray(data.prints) && data.prints.length > 0) {
            const actP = data.prints[0];
            await fetch(`http://localhost:8000/api/sammlung/hinzufuegen`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ benutzername: currentUser, karten_name: data.name, album_name: "Wunschliste", bild_url: actP?.bild_url || "", preis: actP?.preis && actP.preis !== "N/A" ? String(actP.preis) : "0.00" })
            });
            setWishlistSearch("");
            ladeSammlung();
        } else {
            alert("Fehler: API hat keine Druck-Versionen für diese Karte geliefert.");
        }
    } catch(e) { alert("Verbindungsfehler."); }
    setIsWishlistAdding(false);
  }

  const handleMassImport = async () => {
    if(!importText.trim()) return alert("Die Liste ist leer.");
    const targetAlbum = importAlbum === "select" ? "Importiertes Album" : (importAlbum === "NEW" ? newImportAlbumName : importAlbum);
    if(importAlbum === "NEW" && !newImportAlbumName.trim()) return alert("Bitte neuen Albumnamen eingeben.");
    
    setIsImporting(true);
    const lines = importText.split('\n');
    const cardsToAdd = [];
    
    for(let line of lines) {
        line = line.trim();
        if(!line) continue;
        const match = line.match(/^(\d+)x?\s+(.*)$/i);
        let count = 1;
        let name = line;
        if(match) {
            count = parseInt(match[1]);
            name = match[2].trim();
        }
        for(let i=0; i<count; i++) cardsToAdd.push(name);
    }

    const uniqueNames = [...new Set(cardsToAdd)];
    const scryfallData = {};
    for(let i=0; i<uniqueNames.length; i+=75) {
         const chunk = uniqueNames.slice(i, i+75).map(n => ({name: n}));
         try {
             const res = await fetch("https://api.scryfall.com/cards/collection", {
                 method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({identifiers: chunk})
             });
             if(res.ok) {
                 const data = await res.json();
                 if(data && Array.isArray(data.data)) {
                     data.data.forEach(c => {
                         scryfallData[(c?.name || "").toLowerCase()] = {
                             bild_url: c?.image_uris?.normal || (c?.card_faces ? c.card_faces[0]?.image_uris?.normal : ""),
                             preis: c?.prices?.eur || "0.00",
                             echterName: c?.name
                         };
                     });
                 }
             }
         } catch(e) {}
    }

    for(let name of cardsToAdd) {
         const cardInfo = scryfallData[name.toLowerCase()] || {bild_url: "https://via.placeholder.com/180", preis: "0.00", echterName: name};
         await fetch(`http://localhost:8000/api/sammlung/hinzufuegen`, {
             method: "POST", headers: { "Content-Type": "application/json" },
             body: JSON.stringify({
                 benutzername: currentUser,
                 karten_name: cardInfo.echterName,
                 album_name: targetAlbum,
                 bild_url: cardInfo.bild_url || "https://via.placeholder.com/180",
                 preis: String(cardInfo.preis || "0.00")
             })
         });
    }
    
    setIsImporting(false);
    setImportText("");
    alert(`Import von ${cardsToAdd.length} Karten erfolgreich abgeschlossen!`);
    navigate('/sammlung?tab=alben');
    ladeSammlung();
  }

  const exportiereSammlung = () => {
    let csvContent = "Kartenname;Album;Preis (EUR)\n";
    Object.entries(portfolioAlben).forEach(([albumName, karten]) => {
      if(Array.isArray(karten)) {
          karten.forEach(k => {
            if(k) csvContent += `"${k.name || ""}";"${albumName}";"${k.livePreis || k.preis || "0.00"}"\n`;
          });
      }
    });
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "MTG_Pro_Sammlung.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const existingPortfolioAlbumNames = Object.keys(portfolioAlben || {});

  return (
    <div className="apple-main-container">
      <h2>Portfolio & Alben.</h2>
      <p style={{marginBottom: '40px', fontSize: '1.2rem'}}>Verwalte deine Sammlung, Werte und Einkaufslisten.</p>

      <div className="segmented-control">
        <button className={`segment-btn ${currentTab === 'alben' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=alben')}>Alben & Verwaltung</button>
        <button className={`segment-btn ${currentTab === 'dashboard' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=dashboard')}>Finanz-Dashboard</button>
        <button className={`segment-btn ${currentTab === 'wishlist' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=wishlist')}>Wunschliste</button>
        <button className={`segment-btn ${currentTab === 'import' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=import')}>Massen-Import</button>
        <button className={`segment-btn ${currentTab === 'export' ? 'active' : ''}`} onClick={() => navigate('/sammlung?tab=export')}>Export</button>
      </div>
      
      {currentTab === 'alben' && (
        <>
          <div style={{display: 'flex', gap: '15px', maxWidth: '600px', marginBottom: '60px', background: 'var(--bg-card)', padding: '25px', borderRadius: '20px', border: '1px solid var(--border-color)', boxShadow: '0 8px 30px var(--shadow-color)'}}>
            <input placeholder="Neuer Albumname..." value={newAlbumName} onChange={e => setNewAlbumName(e.target.value)} style={{background: 'var(--input-bg)', border: 'none'}} />
            <button className="primary-btn" onClick={erstelleLeeresAlbum}>Erstellen</button>
          </div>

          {Object.keys(portfolioAlben).length === 0 ? <p>Deine Sammlung ist noch leer. Importiere Karten oder suche nach ihnen!</p> : Object.keys(portfolioAlben).map((albumName) => {
            const karten = portfolioAlben[albumName];
            const sortMethod = sortOrders[albumName] || "default";
            const sortedKarten = sortiereKarten(karten, sortMethod);

            return (
              <div key={albumName} className="content-card" style={{padding: '40px'}}>
                <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '20px', marginBottom: '30px', flexWrap: 'wrap', gap: '20px'}}>
                  <div style={{display: 'flex', alignItems: 'center', gap: '20px'}}>
                    <h3 style={{margin: 0, fontSize: '1.8rem'}}>{albumName}</h3>
                    
                    <select 
                      value={sortMethod} 
                      onChange={(e) => setSortOrders({...sortOrders, [albumName]: e.target.value})}
                      style={{padding: '8px 12px', fontSize: '0.9rem', width: 'auto', borderRadius: '8px', background: 'var(--btn-secondary)', border: 'none', cursor: 'pointer'}}
                    >
                      <option value="default">Zuletzt hinzugefügt</option>
                      <option value="priceDesc">Preis: Absteigend</option>
                      <option value="priceAsc">Preis: Aufsteigend</option>
                      <option value="az">Alphabetisch (A-Z)</option>
                    </select>

                    <button className="danger-btn-subtle" onClick={() => loescheGanzesAlbum(albumName)}>Löschen</button>
                  </div>
                  <div style={{textAlign: 'right'}}>
                    <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}> Marktwert {updatingPrices && <span style={{color: 'var(--text-main)'}}>(Live...)</span>}</span>
                    <span style={{color: 'var(--price-color)', fontWeight: 600, fontSize: '1.6rem'}}>{berechneAlbumWert(karten)} €</span>
                  </div>
                </div>
                
                {sortedKarten.length === 0 ? (
                  <p style={{color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '40px 0'}}>Dieses Album ist leer.</p>
                ) : (
                  <div className="gallery-grid" style={{marginTop: 0}}>
                    {sortedKarten.map((karte, idx) => {
                      if(!karte) return null;
                      return (
                      <div key={karte?.id || idx} className="gallery-item">
                        <button className="gallery-remove-btn" onClick={() => loescheKarte(karte.id)}>✕</button>
                        <img src={karte?.bild_url || "https://via.placeholder.com/180"} alt={karte?.name || "Unbekannt"} className="gallery-img" />
                        <span style={{fontWeight: 600, fontSize: '0.95rem', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '5px'}} title={karte?.name}>{karte?.name}</span>
                        <span className="gallery-price-tag">{karte?.livePreis || karte?.preis || "0.00"} €</span>
                      </div>
                    )})}
                  </div>
                )}
              </div>
            );
          })}
        </>
      )}

      {currentTab === 'dashboard' && (
        <div className="dashboard-grid">
           <div>
              <div className="content-card" style={{padding: '40px'}}>
                <h3 style={{fontSize: '1.2rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '10px'}}>Gesamter Marktwert (Ohne Wunschliste)</h3>
                <h1 style={{fontSize: '4.5rem', margin: '0 0 30px 0', color: 'var(--text-main)', letterSpacing: '-0.04em'}}>{totalPortfolioWert} €</h1>
                
                <h4 style={{marginBottom: '15px', color: 'var(--text-muted)'}}>Wertverteilung nach Alben</h4>
                {Object.entries(portfolioAlben).map(([name, karten]) => {
                   const val = parseFloat(berechneAlbumWert(karten));
                   if(val === 0) return null;
                   const total = parseFloat(totalPortfolioWert) || 1; 
                   const pct = Math.round((val / total) * 100) || 0;
                   return (
                     <div key={name} style={{marginBottom: '15px'}}>
                        <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '5px', fontSize: '0.95rem'}}>
                          <span style={{fontWeight: 600}}>{name}</span>
                          <span>{val.toFixed(2)} € ({pct}%)</span>
                        </div>
                        <div style={{width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden'}}>
                          <div style={{width: `${pct}%`, height: '100%', background: 'var(--accent-color)'}}></div>
                        </div>
                     </div>
                   )
                })}
              </div>
           </div>

           <div>
              <div className="content-card" style={{padding: '30px'}}>
                <h3 style={{marginBottom: '20px', fontSize: '1.5rem'}}>Top 10 Wertvollste Karten</h3>
                <div style={{display: 'flex', flexDirection: 'column'}}>
                  {getAllCardsFlat()
                    .sort((a,b) => getPriceVal(b) - getPriceVal(a))
                    .slice(0, 10)
                    .map((k, i) => (
                    <div key={i} className="top-card-item">
                      <span style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text-muted)', width: '30px' }}>#{i+1}</span>
                      <img src={k?.bild_url || "https://via.placeholder.com/180"} alt={k?.name || "Unbekannt"} className="top-card-img" />
                      <div style={{ flexGrow: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--text-main)' }}>{k?.name}</div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>In: {k?.albumName}</div>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: '1.1rem', color: 'var(--price-color)' }}>{k?.livePreis || k?.preis || "0.00"} €</div>
                    </div>
                  ))}
                  {getAllCardsFlat().length === 0 && <p>Keine Karten im Portfolio.</p>}
                </div>
              </div>
           </div>
        </div>
      )}

      {currentTab === 'wishlist' && (
        <div className="content-card" style={{padding: '40px'}}>
           <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border-color)', paddingBottom: '20px', marginBottom: '30px', flexWrap: 'wrap', gap: '20px'}}>
              <div>
                 <h3 style={{margin: 0, fontSize: '2rem'}}>Meine Wunschliste</h3>
                 <p style={{margin: '5px 0 0 0'}}>Diese Karten sind von deinem Finanz-Dashboard ausgeschlossen.</p>
              </div>
              <div style={{textAlign: 'right'}}>
                 <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}>Benötigtes Budget</span>
                 <span style={{color: 'var(--accent-color)', fontWeight: 600, fontSize: '1.6rem'}}>{totalWishlistWert} €</span>
              </div>
           </div>

           <div style={{display: 'flex', gap: '15px', maxWidth: '600px', marginBottom: '40px', background: 'var(--bg-main)', padding: '15px', borderRadius: '16px'}}>
              <input 
                 placeholder="Kartenname eingeben (z.B. The One Ring)..." 
                 value={wishlistSearch} 
                 onChange={e => setWishlistSearch(e.target.value)} 
                 onKeyDown={(e) => e.key === 'Enter' && addToWishlist()}
                 style={{background: 'var(--input-bg)', border: '1px solid var(--border-color)'}} 
              />
              <button className="primary-btn" onClick={addToWishlist}>{isWishlistAdding ? "Sucht..." : "Hinzufügen"}</button>
           </div>

           {wishlistKarten.length === 0 ? (
             <p style={{color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center', padding: '40px 0'}}>Deine Wunschliste ist leer.</p>
           ) : (
             <div className="gallery-grid" style={{marginTop: 0}}>
               {sortiereKarten(wishlistKarten, "priceDesc").map((karte, idx) => {
                 if(!karte) return null;
                 return (
                 <div key={karte?.id || idx} className="gallery-item">
                   <button className="gallery-remove-btn" onClick={() => loescheKarte(karte.id)}>✕</button>
                   <img src={karte?.bild_url || "https://via.placeholder.com/180"} alt={karte?.name || "Unbekannt"} className="gallery-img" />
                   <span style={{fontWeight: 600, fontSize: '0.95rem', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '5px'}} title={karte?.name}>{karte?.name}</span>
                   <span className="gallery-price-tag" style={{color: 'var(--text-main)', background: 'var(--bg-main)'}}>{karte?.livePreis || karte?.preis || "0.00"} €</span>
                 </div>
               )})}
             </div>
           )}
        </div>
      )}

      {currentTab === 'import' && (
        <div className="content-card" style={{padding: '40px', maxWidth: '1000px', margin: '0 auto'}}>
           <h3 style={{fontSize: '2rem', marginBottom: '10px'}}>Massen-Import (CSV / Text)</h3>
           <p style={{marginBottom: '30px'}}>Kopiere eine Liste von Karten (z.B. aus Moxfield oder Manabox) in das Textfeld. Wir suchen alle Bilder und Live-Preise vollautomatisch für dich zusammen.</p>
           
           <textarea 
             placeholder="1x Sol Ring&#10;4x Lightning Bolt&#10;1x The One Ring..." 
             value={importText} 
             onChange={e => setImportText(e.target.value)} 
             style={{height: '300px', background: 'var(--bg-main)', fontFamily: 'monospace', marginBottom: '25px'}} 
           />

           <div style={{display: 'flex', gap: '20px', alignItems: 'center', background: 'var(--btn-secondary)', padding: '25px', borderRadius: '16px', flexWrap: 'wrap'}}>
              <div style={{flexGrow: 1}}>
                 <span style={{display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '10px'}}>Ziel-Album auswählen</span>
                 <div style={{display: 'flex', gap: '15px'}}>
                    <select 
                      value={importAlbum} 
                      onChange={e => setImportAlbum(e.target.value)} 
                      style={{padding: '14px', flexGrow: 1, border: 'none', background: 'var(--input-bg)'}}
                    >
                      <option value="select" disabled>Bitte Album wählen...</option>
                      {(existingPortfolioAlbumNames || []).map(a => <option key={a} value={a}>{a}</option>)}
                      <option value="NEW">+ Neues Album erstellen...</option>
                    </select>
                    {importAlbum === "NEW" && (
                      <input 
                        type="text" 
                        placeholder="Name des neuen Albums..." 
                        value={newImportAlbumName} 
                        onChange={e => setNewImportAlbumName(e.target.value)} 
                        style={{padding: '14px', flexGrow: 1, border: 'none', background: 'var(--input-bg)'}} 
                      />
                    )}
                 </div>
              </div>
              <button 
                className="primary-btn" 
                onClick={handleMassImport} 
                disabled={isImporting}
                style={{padding: '16px 40px', marginTop: '15px'}}
              >
                {isImporting ? "Importiere Daten..." : "Karten Importieren"}
              </button>
           </div>
        </div>
      )}

      {currentTab === 'export' && (
        <div className="content-card" style={{padding: '60px 40px', maxWidth: '800px', margin: '0 auto', textAlign: 'center'}}>
           <h3 style={{fontSize: '2.5rem', marginBottom: '15px'}}>Sammlung exportieren</h3>
           <p style={{marginBottom: '40px', fontSize: '1.1rem', color: 'var(--text-muted)'}}>
             Lade deine komplette Sammlung als CSV-Datei herunter. Ideal als Backup, für Excel-Tabellen oder für Versicherungszwecke.
           </p>
           <button className="primary-btn" onClick={exportiereSammlung} style={{padding: '18px 40px', fontSize: '1.2rem'}}>
              <Icons.ExternalLink /> Als CSV herunterladen
           </button>
        </div>
      )}

    </div>
  )
}

function DecksView({ currentUser }) {
  const [decks, setDecks] = useState([]);
  const [selectedDeck, setSelectedDeck] = useState(null);
  
  const [newDeckName, setNewDeckName] = useState("");
  const [importListe, setImportListe] = useState("");
  const [viewMode, setViewMode] = useState("text"); 
  const [visualDeck, setVisualDeck] = useState(null);
  const [playtest, setPlaytest] = useState(null);

  const [laedt, setLaedt] = useState(false);
  const [analyse, setAnalyse] = useState(null);
  const [stats, setStats] = useState(null);
  const [deckWert, setDeckWert] = useState(null);
  const [quickSearch, setQuickSearch] = useState("");
  const [quickResult, setQuickResult] = useState(null);

  const ladeDecks = async () => {
    try { 
      const res = await fetch(`http://localhost:8000/api/decks/${currentUser}`); 
      const data = await res.json();
      if(Array.isArray(data)) setDecks(data); else setDecks([]);
    } catch { setDecks([]); }
  };

  const erstelleDeck = async () => {
    if(!newDeckName) return;
    await fetch(`http://localhost:8000/api/decks/erstellen`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ benutzername: currentUser, deck_name: newDeckName, deck_liste: importListe }) });
    setNewDeckName(""); setImportListe(""); ladeDecks();
  };

  const speichereListe = async () => {
    await fetch(`http://localhost:8000/api/decks/update`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_id: selectedDeck.id, deck_liste: selectedDeck.liste }) });
    alert("Deck gespeichert.");
  };

  const handleQuickSearch = async () => {
    if(!quickSearch) return;
    const res = await fetch(`http://localhost:8000/api/suche/${quickSearch}`);
    const data = await res.json();
    if(!data.error) setQuickResult(data); else alert("Nicht gefunden.");
  };

  const addCardToTextarea = () => {
    if(!quickResult) return;
    const aktuelleListe = selectedDeck.liste ? selectedDeck.liste + "\n" : "";
    setSelectedDeck({ ...selectedDeck, liste: aktuelleListe + `1x ${quickResult.name}` });
    setQuickSearch(""); setQuickResult(null);
    setVisualDeck(null); setStats(null); setAnalyse(null); setDeckWert(null);
  };

  const ladeStatsUndAnalyse = async () => {
    if (!selectedDeck.liste || !selectedDeck.liste.trim()) {
        alert("Dein Deck ist noch leer! Bitte füge zuerst im Text-Editor Karten hinzu.");
        return;
    }
    setViewMode("stats");
    if (stats && analyse && deckWert && !laedt) return;
    setLaedt(true);
    
    const p1 = !analyse ? fetch(`http://localhost:8000/api/deck/analyse`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) })
        .then(res => res.json()).then(data => setAnalyse(data)).catch(() => setAnalyse({error: "KI nicht erreichbar."})) : Promise.resolve();

    const p2 = !deckWert ? fetch(`http://localhost:8000/api/deck/wert`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) })
        .then(res => res.json()).then(data => setDeckWert(data)).catch(() => {}) : Promise.resolve();

    const p3 = !stats ? fetch(`http://localhost:8000/api/deck/stats`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) })
        .then(res => res.json()).then(data => setStats(data)).catch(() => {}) : Promise.resolve();

    await Promise.all([p1, p2, p3]);
    setLaedt(false);
  };

  const ladeVisuelleAnsicht = async (mode) => {
    if (!selectedDeck.liste || !selectedDeck.liste.trim()) {
        alert("Dein Deck ist noch leer! Bitte füge zuerst im Text-Editor Karten hinzu.");
        return;
    }
    setViewMode(mode);
    if(visualDeck && visualDeck.length > 0) return;
    setLaedt(true);
    try {
      const res = await fetch(`http://localhost:8000/api/deck/visualize`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ deck_liste: selectedDeck.liste }) });
      const data = await res.json();
      if(data && Array.isArray(data.karten)) setVisualDeck(data.karten);
    } catch { alert("Fehler beim Laden der Bilder."); }
    setLaedt(false);
  };

  const startPlaytest = () => {
    if(!visualDeck || !Array.isArray(visualDeck) || visualDeck.length === 0) {
        alert("Dein Deck konnte nicht visualisiert werden.");
        return;
    }
    let deckArray = [];
    visualDeck.forEach(k => { if(k && k.name && !k.name.includes("(Nicht gefunden)")) { for(let i=0; i<(k.count||1); i++) deckArray.push(k); }});
    for (let i = deckArray.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [deckArray[i], deckArray[j]] = [deckArray[j], deckArray[i]];
    }
    setPlaytest({ hand: deckArray.slice(0, 7), library: deckArray.slice(7), mulligans: 0 });
  };

  const doMulligan = () => {
    let deckArray = [];
    visualDeck.forEach(k => { if(k && k.name && !k.name.includes("(Nicht gefunden)")) { for(let i=0; i<(k.count||1); i++) deckArray.push(k); }});
    for (let i = deckArray.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [deckArray[i], deckArray[j]] = [deckArray[j], deckArray[i]];
    }
    const nextMulligans = playtest.mulligans + 1;
    const drawCount = Math.max(0, 7 - nextMulligans);
    setPlaytest({ hand: deckArray.slice(0, drawCount), library: deckArray.slice(drawCount), mulligans: nextMulligans });
  };

  const drawCard = () => {
    if(!playtest || !playtest.library || playtest.library.length === 0) return;
    const newHand = [...playtest.hand, playtest.library[0]];
    const newLibrary = playtest.library.slice(1);
    setPlaytest({ hand: newHand, library: newLibrary, mulligans: playtest.mulligans });
  };

  const holeAlleProxyKarten = () => {
    if(!visualDeck) return [];
    const proxyCards = [];
    visualDeck.forEach(k => {
        if(k && k.name && !k.name.includes("(Nicht gefunden)")) {
            const count = k.count || 1;
            for(let i=0; i<count; i++) proxyCards.push(k);
        }
    });
    return proxyCards;
  }

  useEffect(() => { ladeDecks(); }, []);

  const colorMap = { "W": {bg: "#F0E6D2", text: "#000"}, "U": {bg: "#0E68AB", text: "#FFF"}, "B": {bg: "#150B00", text: "#FFF"}, "R": {bg: "#D3202A", text: "#FFF"}, "G": {bg: "#00733E", text: "#FFF"}, "C": {bg: "#C0C0C0", text: "#000"} };

  const renderGruppierteKarten = () => {
    if(!visualDeck || !Array.isArray(visualDeck) || visualDeck.length === 0) return <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Kartenbilder gefunden. Bitte prüfe die Namen im Editor.</p>;
    
    const grouped = { Unbekannt: [], Kommander: [], Kreaturen: [], Artefakte: [], Hexereien_Spontanzauber: [], Verzauberungen: [], Länder: [] };
    
    visualDeck.forEach(k => {
       if(!k) return;
       const t = (k.type || "").toLowerCase();
       if(k.name && k.name.includes("(Nicht gefunden)")) grouped.Unbekannt.push(k);
       else if(t.includes('legendary creature') && grouped.Kommander.length === 0) grouped.Kommander.push(k);
       else if(t.includes('creature')) grouped.Kreaturen.push(k);
       else if(t.includes('artifact')) grouped.Artefakte.push(k);
       else if(t.includes('instant') || t.includes('sorcery')) grouped.Hexereien_Spontanzauber.push(k);
       else if(t.includes('enchantment')) grouped.Verzauberungen.push(k);
       else if(t.includes('land')) grouped.Länder.push(k);
       else grouped.Unbekannt.push(k);
    });

    return Object.entries(grouped).map(([gruppe, karten]) => {
      if(!karten || karten.length === 0) return null;
      return (
        <div key={gruppe}>
          <h4 className="deck-group-title" style={{color: gruppe === 'Unbekannt' ? 'var(--danger-color)' : 'inherit'}}>
            {gruppe.replace('_', ' & ')} ({karten.reduce((acc, k) => acc + (k.count || 1), 0)})
          </h4>
          <div className="gallery-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '15px'}}>
            {karten.map((k, idx) => {
              if(!k) return null;
              return (
              <div key={k.name || idx} className="deck-card-wrapper">
                <img src={k.image || "https://via.placeholder.com/180"} alt={k.name || "Unbekannt"} className="deck-card-img" style={{ border: gruppe === 'Unbekannt' ? '2px solid var(--danger-color)' : 'none' }} />
                <div className="card-badge">{k.count || 1}x</div>
              </div>
            )})}
          </div>
        </div>
      );
    });
  };

  return (
    <div className="apple-main-container">
      {!selectedDeck ? (
        <>
          <h2>Deck-Center.</h2>
          <p style={{fontSize: '1.2rem', marginBottom: '40px'}}>Baue Decks, importiere Listen und bereite sie für den Druck vor.</p>
          
          <div className="content-card" style={{marginBottom: '50px', padding: '30px'}}>
            <h4 style={{marginBottom: '15px'}}>Neues Deck erstellen</h4>
            <div style={{display: 'flex', gap: '15px', marginBottom: '15px'}}>
              <input placeholder="Deckname..." value={newDeckName} onChange={e => setNewDeckName(e.target.value)} style={{background: 'var(--input-bg)'}} />
            </div>
            <textarea placeholder="Optional: Kopiere hier direkt eine komplette Deckliste hinein..." value={importListe} onChange={e => setImportListe(e.target.value)} style={{height: '100px', background: 'var(--input-bg)', marginBottom: '15px'}} />
            <button className="primary-btn" onClick={erstelleDeck}>Deck anlegen</button>
          </div>

          <div className="gallery-grid" style={{gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))'}}>
            {(decks || []).map((d, idx) => {
              if(!d) return null;
              return (
              <div key={d.id || idx} className="content-card" onClick={() => { setSelectedDeck(d); setAnalyse(null); setDeckWert(null); setStats(null); setViewMode("text"); setVisualDeck(null); }} style={{cursor: 'pointer', textAlign: 'center', transition: 'transform 0.2s', padding: '35px'}}>
                <h3 style={{fontSize: '1.5rem'}}>{d.name}</h3><p style={{margin: 0}}>Öffnen & Bearbeiten</p>
              </div>
            )})}
          </div>
        </>
      ) : (
        <div>
          <button onClick={() => {setSelectedDeck(null); ladeDecks();}} style={{background: 'none', color: 'var(--text-muted)', border: 'none', cursor: 'pointer', padding: 0, marginBottom: '30px', fontSize: '1.05rem', fontWeight: 500}}>← Zurück zur Übersicht</button>
          
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', borderBottom: '1px solid var(--border-color)', paddingBottom: '20px', marginBottom: '30px'}}>
            <h2 style={{margin: 0, fontSize: '3rem', letterSpacing: '-0.03em'}}>{selectedDeck?.name}</h2>
          </div>

          <div className="segmented-control" style={{marginBottom: '40px', display: 'flex', justifyContent: 'center'}}>
            <button className={`segment-btn ${viewMode === 'text' ? 'active' : ''}`} onClick={() => setViewMode("text")}>Text-Editor</button>
            <button className={`segment-btn ${viewMode === 'visual' ? 'active' : ''}`} onClick={() => ladeVisuelleAnsicht("visual")}>Visueller Builder</button>
            <button className={`segment-btn ${viewMode === 'stats' ? 'active' : ''}`} onClick={ladeStatsUndAnalyse}>Analyse & Stats</button>
            <button className={`segment-btn ${viewMode === 'proxy' ? 'active' : ''}`} onClick={() => ladeVisuelleAnsicht("proxy")}>Proxy-Druck</button>
          </div>
          
          {viewMode === "text" && (
            <div className="split-editor-container">
              <div>
                <textarea 
                   className="deck-textarea" 
                   value={selectedDeck?.liste || ""} 
                   onChange={e => {
                     setSelectedDeck({...selectedDeck, liste: e.target.value});
                     setVisualDeck(null); setStats(null); setAnalyse(null); setDeckWert(null);
                   }} 
                   placeholder="1x Sol Ring..." 
                   style={{padding: '25px', borderRadius: '20px'}} 
                />
                <div style={{marginTop: '25px', display: 'flex', gap: '15px', flexWrap: 'wrap'}}>
                  <button className="primary-btn" onClick={speichereListe}>Änderungen speichern</button>
                  <button className="secondary-btn" onClick={() => {
                      navigator.clipboard.writeText(selectedDeck?.liste || "");
                      alert("Deckliste kopiert! (Bereit für MTG Arena)");
                  }}>Kopieren (Arena Export)</button>
                </div>
              </div>
              <div className="content-card" style={{margin: 0, background: 'var(--btn-secondary)', boxShadow: 'none', border: '1px solid var(--border-color)'}}>
                <h4 style={{fontSize: '1.2rem', marginBottom: '15px'}}>Karten manuell hinzufügen</h4>
                <div style={{display: 'flex', gap: '10px', marginBottom: '15px'}}>
                  <input placeholder="Kartenname (z.B. Sol Ring)..." value={quickSearch} onChange={e => setQuickSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleQuickSearch()} style={{background: 'var(--bg-card)', border: 'none'}} />
                  <button className="primary-btn" onClick={handleQuickSearch}>Suchen</button>
                </div>
                {quickResult && (
                  <div style={{textAlign: 'center', background: 'var(--bg-card)', padding: '25px', borderRadius: '16px', boxShadow: '0 4px 15px rgba(0,0,0,0.03)'}}>
                    <img src={quickResult?.bild_url || "https://via.placeholder.com/180"} alt={quickResult?.name || "Unbekannt"} style={{width: '150px', borderRadius: '4.75% / 3.5%', marginBottom: '15px', boxShadow: '0 4px 10px rgba(0,0,0,0.1)'}} />
                    <div style={{fontWeight: 600, fontSize: '1.1rem'}}>{quickResult?.name}</div>
                    <div style={{color: 'var(--price-color)', marginBottom: '15px', fontSize: '1.1rem', fontWeight: 600}}>{quickResult?.preis || "0.00"} €</div>
                    <button className="primary-btn" style={{width: '100%'}} onClick={addCardToTextarea}>+ Zur Liste hinzufügen</button>
                  </div>
                )}
              </div>
            </div>
          )}

          {viewMode === "visual" && (
            <div className="content-card" style={{padding: '40px'}}>
              {laedt ? <div className="spinner"></div> : (
                <>
                  {(!visualDeck || visualDeck.length === 0) ? (
                     <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Karten gefunden. Hast du Namen im Editor eingegeben?</p>
                  ) : (
                    <>
                      <div style={{textAlign: 'right', marginBottom: '20px'}}>
                        <button className="primary-btn" style={{padding: '16px 30px', fontSize: '1.1rem'}} onClick={startPlaytest}>
                           <Icons.Sparkles /> Starthand Simulator starten
                        </button>
                      </div>
                      {renderGruppierteKarten()}
                    </>
                  )}
                </>
              )}
            </div>
          )}

          {viewMode === "stats" && (
            <div className="content-card" style={{padding: '40px', animation: 'fadeIn 0.6s ease'}}>
              {laedt ? <div style={{textAlign: 'center', padding: '60px'}}><div className="spinner"></div><p style={{marginTop: '20px'}}>KI berechnet Strategie und Manakurve...</p></div> : (
                <>
                  <h3 style={{marginBottom: '40px', fontSize: '2.2rem'}}>Deck Statistiken</h3>
                  
                  {stats && stats.cmc && Object.keys(stats.cmc).length > 0 ? (
                      <div style={{display: 'flex', flexWrap: 'wrap', gap: '60px', marginBottom: '60px'}}>
                        <div style={{flexGrow: 1}}>
                          <h4 style={{color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em'}}>Mana-Kurve (CMC)</h4>
                          <div className="bar-chart-container">
                            {Object.keys(stats?.cmc || {}).sort((a,b) => parseInt(a)-parseInt(b)).map(cmc => (
                              <div key={cmc} className="bar-column">
                                <span style={{fontSize: '0.9rem', fontWeight: 600}}>{stats.cmc[cmc]}</span>
                                <div className="bar" style={{height: Math.min(stats.cmc[cmc] * 12, 100) + 'px'}}></div>
                                <span style={{fontSize: '0.85rem', color: 'var(--text-muted)'}}>CMC {cmc}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                        
                        <div style={{flexGrow: 1}}>
                          <h4 style={{color: 'var(--text-muted)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em'}}>Farb-Identität</h4>
                          <div className="color-circles">
                            {Object.keys(stats?.colors || {}).filter(c => stats.colors[c] > 0).map(c => (
                              <div key={c} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px'}}>
                                <div className="color-circle" style={{background: colorMap[c]?.bg || '#000', color: colorMap[c]?.text || '#FFF'}}>
                                  {c}
                                </div>
                                <span style={{fontSize: '1rem', fontWeight: 600}}>{stats.colors[c]}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                  ) : (
                      <p style={{color: 'var(--text-muted)', marginBottom: '40px'}}>Keine Statistiken verfügbar. Ist das Deck leer?</p>
                  )}

                  {analyse && !analyse.error && analyse.strategie && (
                      <div style={{borderTop: '1px solid var(--border-color)', paddingTop: '40px'}}>
                          <h3 style={{fontSize: '2rem', marginBottom: '30px'}}>KI-Evaluation: <span style={{color: 'var(--text-main)'}}>{analyse.commander || "Das Deck"}</span></h3>
                          
                          <div style={{background: 'var(--btn-secondary)', padding: '25px', borderRadius: '16px', marginBottom: '30px'}}>
                            <span style={{fontSize: '0.85rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, display: 'block', marginBottom: '10px'}}>Strategie</span>
                            <p style={{color: 'var(--text-main)', fontSize: '1.05rem', margin: 0}}>{analyse.strategie}</p>
                          </div>

                          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '30px', marginBottom: '30px'}}>
                            <div>
                              <h4 style={{color: 'var(--text-main)', fontSize: '1.2rem', marginBottom: '15px'}}>Stärken</h4>
                              <ul style={{color: 'var(--text-main)', paddingLeft: '20px', margin: 0, fontSize: '1.05rem', lineHeight: '1.6'}}>
                                {Array.isArray(analyse.staerken) && analyse.staerken.map((s, i) => <li key={i} style={{marginBottom: '8px'}}>{s}</li>)}
                              </ul>
                            </div>
                            <div>
                              <h4 style={{color: 'var(--text-muted)', fontSize: '1.2rem', marginBottom: '15px'}}>Schwächen</h4>
                              <ul style={{color: 'var(--text-main)', paddingLeft: '20px', margin: 0, fontSize: '1.05rem', lineHeight: '1.6'}}>
                                {Array.isArray(analyse.schwaechen) && analyse.schwaechen.map((s, i) => <li key={i} style={{marginBottom: '8px'}}>{s}</li>)}
                              </ul>
                            </div>
                          </div>

                          <div style={{borderTop: '1px solid var(--border-color)', paddingTop: '30px'}}>
                            <h4 style={{fontSize: '1.3rem', marginBottom: '20px'}}>Detektierte Hauptcombos</h4>
                            {Array.isArray(analyse.combos) && analyse.combos.map((c, i) => (
                              <div key={i} style={{background: 'var(--bg-card)', border: '1px solid var(--border-color)', padding: '20px', borderRadius: '12px', marginBottom: '15px'}}>
                                <strong style={{display: 'block', fontSize: '1.1rem', marginBottom: '8px'}}>{c?.karten}</strong>
                                <span style={{color: 'var(--text-muted)', fontSize: '1rem'}}>{c?.erklaerung}</span>
                              </div>
                            ))}
                          </div>
                      </div>
                  )}

                  {analyse && analyse.error && (
                      <div style={{background: 'var(--danger-bg)', color: 'var(--danger-color)', padding: '20px', borderRadius: '12px', textAlign: 'center'}}>
                          {analyse.error}
                      </div>
                  )}

                  {deckWert && (
                    <div style={{marginTop: '50px', paddingTop: '30px', borderTop: '1px solid var(--border-color)', textAlign: 'right'}}>
                      <span style={{fontSize: '0.95rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginRight: '15px', letterSpacing: '0.05em'}}>Geschätzter Marktwert</span>
                      <span style={{color: 'var(--price-color)', fontWeight: 600, fontSize: '2.5rem', letterSpacing: '-0.04em'}}>{deckWert?.gesamt_wert || "0.00"} €</span>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {viewMode === "proxy" && (
            <div className="content-card" style={{padding: '40px'}}>
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px'}}>
                 <div>
                   <h3 style={{fontSize: '2rem', margin: 0}}>Proxy-Druck (PDF)</h3>
                   <p style={{margin: '5px 0 0 0', color: 'var(--text-muted)'}}>Drucke diese Seite im A4-Format (ohne Ränder). Die Karten haben exakte Turnier-Maße (63x88mm).</p>
                 </div>
                 {visualDeck && visualDeck.length > 0 && (
                     <button className="primary-btn" onClick={() => window.print()}><Icons.ExternalLink /> Jetzt Drucken</button>
                 )}
              </div>
              
              {laedt ? <div className="spinner"></div> : (
                (!visualDeck || visualDeck.length === 0) ? (
                   <p style={{textAlign: 'center', color: 'var(--text-muted)'}}>Keine Karten zum Drucken gefunden. Füge zuerst Karten in den Editor ein.</p>
                ) : (
                    <div className="proxy-print-area">
                      <div className="proxy-preview-grid">
                          {holeAlleProxyKarten().map((k, i) => (
                            <img key={i} src={k?.image || "https://via.placeholder.com/180"} alt={k?.name} className="proxy-print-img" style={{width: '100%', borderRadius: '4.75% / 3.5%'}} />
                          ))}
                      </div>
                    </div>
                )
              )}
            </div>
          )}

          {/* ERWEITERTER STARTHAND SIMULATOR MODAL */}
          {playtest && (
            <div className="modal-overlay" onClick={() => setPlaytest(null)}>
              <div className="modal-content" style={{maxWidth: '1200px', background: 'var(--bg-main)'}} onClick={e => e.stopPropagation()}>
                <button className="close-btn" onClick={() => setPlaytest(null)}>✕</button>
                
                <h2 style={{marginBottom: '5px', fontSize: '2.5rem', textAlign: 'center'}}>Starthand Simulator</h2>
                <p style={{textAlign: 'center', color: 'var(--text-muted)', marginBottom: '40px'}}>
                   Karten in der Bibliothek: <strong style={{color: 'var(--text-main)'}}>{(playtest.library || []).length}</strong> | Genommene Mulligans: <strong style={{color: 'var(--danger-color)'}}>{playtest.mulligans}</strong>
                </p>

                <div className="playtest-hand-container">
                  {(playtest.hand || []).map((k, i) => (
                    <img 
                      key={i} 
                      src={k?.image || "https://via.placeholder.com/180"} 
                      alt={k?.name || "Unbekannt"} 
                      className="playtest-card" 
                      style={{zIndex: i}} 
                    />
                  ))}
                  {(!playtest.hand || playtest.hand.length === 0) && <p style={{color: 'var(--text-muted)'}}>Keine Karten mehr in der Hand.</p>}
                </div>
                
                <div style={{textAlign: 'center', marginTop: '60px', display: 'flex', gap: '20px', justifyContent: 'center'}}>
                  <button className="secondary-btn" style={{padding: '16px 30px', fontSize: '1.1rem'}} onClick={doMulligan}>Mulligan nehmen</button>
                  <button className="primary-btn" style={{padding: '16px 30px', fontSize: '1.1rem'}} onClick={drawCard}>Karte ziehen</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isJudgeOpen, setIsJudgeOpen] = useState(false); 

  useEffect(() => {
    if (isDarkMode) document.body.classList.add('dark-mode');
    else document.body.classList.remove('dark-mode');
  }, [isDarkMode]);

  if (!currentUser) return <><style>{globalStyles}</style><AuthScreen onLoginSuccess={setCurrentUser} /></>;
  
  return (
    <>
      <style>{globalStyles}</style>
      <AppleHeader currentUser={currentUser} setCurrentUser={setCurrentUser} isDarkMode={isDarkMode} setIsDarkMode={setIsDarkMode} setIsJudgeOpen={setIsJudgeOpen} />
      <main><Routes><Route path="/" element={<KartenSuche currentUser={currentUser} />} /><Route path="/sammlung" element={<MeineSammlung currentUser={currentUser} />} /><Route path="/decks" element={<DecksView currentUser={currentUser} />} /></Routes></main>
      <JudgeWidget open={isJudgeOpen} setOpen={setIsJudgeOpen} />
    </>
  );
}
export default App;