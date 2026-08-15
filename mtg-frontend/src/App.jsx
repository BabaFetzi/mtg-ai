import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { setTokens, clearTokens } from './utils/authFetch'
import { FEATURES } from './config'

// Components
import AuthScreen from './components/auth/AuthScreen'
import AppleHeader from './components/layout/AppleHeader'
import EntdeckenHub from './components/entdecken/EntdeckenHub'
import MeineSammlung from './components/sammlung/MeineSammlung'
import DecksView from './components/decks/DecksView'
import SharedDeckView from './components/decks/SharedDeckView'
import PremiumPage from './components/premium/PremiumPage'
import JudgeWidget from './components/layout/JudgeWidget'
import PremiumUpgradeModal from './components/premium/PremiumUpgradeModal'
import LandingPage from './components/layout/LandingPage'
import MobileCamera from './components/playfield/MobileCamera'
import PlayfieldView from './components/playfield/PlayfieldView'
import Footer from './components/layout/Footer'
import { useMeldung } from './components/layout/Meldungen'
import Impressum from './components/legal/Impressum'
import Datenschutz from './components/legal/Datenschutz'
import AGB from './components/legal/AGB'
import PasswortNeu from './components/auth/PasswortNeu'

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

/* --- WUBRG THEMES (Mana-zentriert) --- */
.theme-plains {
  --bg-main: #FAF8F5;
  --bg-card: #FFFFFF;
  --text-main: #2C2B29;
  --text-muted: #8E8A82;
  --border-color: #E6E4DF;
  --nav-bg: rgba(250, 248, 245, 0.8);
  --input-bg: #FFFFFF;
  --btn-secondary: #F3EFEA;
  --btn-secondary-hover: #E8E2D7;
  --shadow-color: rgba(196, 146, 62, 0.05);
  --accent-color: #C4923E;
  --accent-text: #FFFFFF;
  --accent-hover: #A87B2E;
}
.theme-island {
  --bg-main: #070F18;
  --bg-card: #0E1E2F;
  --text-main: #E2ECF5;
  --text-muted: #8AA4C0;
  --border-color: #1A3047;
  --nav-bg: rgba(7, 15, 24, 0.8);
  --input-bg: #0E1E2F;
  --btn-secondary: #14283D;
  --btn-secondary-hover: #1C3854;
  --shadow-color: rgba(0, 113, 227, 0.15);
  --accent-color: #0071E3;
  --accent-text: #FFFFFF;
  --accent-hover: #1D82EC;
}
.theme-swamp {
  --bg-main: #060608;
  --bg-card: #121216;
  --text-main: #E2DCE8;
  --text-muted: #928B9B;
  --border-color: #24242C;
  --nav-bg: rgba(6, 6, 8, 0.8);
  --input-bg: #121216;
  --btn-secondary: #1C1C24;
  --btn-secondary-hover: #262630;
  --shadow-color: rgba(155, 93, 229, 0.15);
  --accent-color: #9B5DE5;
  --accent-text: #FFFFFF;
  --accent-hover: #AF7AEB;
}
.theme-mountain {
  --bg-main: #0E0707;
  --bg-card: #1C0F0F;
  --text-main: #F5E2E2;
  --text-muted: #B88E8E;
  --border-color: #381E1E;
  --nav-bg: rgba(14, 7, 7, 0.8);
  --input-bg: #1C0F0F;
  --btn-secondary: #2C1818;
  --btn-secondary-hover: #3D2222;
  --shadow-color: rgba(255, 77, 77, 0.15);
  --accent-color: #FF4D4D;
  --accent-text: #FFFFFF;
  --accent-hover: #FF6666;
}
.theme-forest {
  --bg-main: #050A06;
  --bg-card: #101F13;
  --text-main: #E2EFE4;
  --text-muted: #8AA890;
  --border-color: #1F3D26;
  --nav-bg: rgba(5, 10, 6, 0.8);
  --input-bg: #101F13;
  --btn-secondary: #18301E;
  --btn-secondary-hover: #22452B;
  --shadow-color: rgba(76, 175, 80, 0.15);
  --accent-color: #4CAF50;
  --accent-text: #FFFFFF;
  --accent-hover: #66BB6A;
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
.pricing-card { transition: transform 0.3s cubic-bezier(0.25, 1, 0.5, 1), box-shadow 0.3s cubic-bezier(0.25, 1, 0.5, 1), border-color 0.3s; }
.pricing-card:hover { transform: translateY(-8px); box-shadow: 0 20px 40px var(--shadow-color); }
.pricing-card.highlighted:hover { border-color: #30D158 !important; }

input, textarea, select {
  width: 100%; background: var(--input-bg); border: 1px solid var(--border-color); color: var(--text-main);
  padding: 16px 20px; border-radius: 12px; font-size: 1.05rem; box-sizing: border-box; transition: all 0.2s; font-family: inherit;
}
input:focus, textarea:focus, select:focus { outline: none; border-color: #0071E3; box-shadow: 0 0 0 4px rgba(0, 113, 227, 0.1); }

.primary-btn { background: var(--accent-color); color: var(--accent-text); border: none; padding: 14px 28px; border-radius: 980px; font-size: 1.05rem; font-weight: 500; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 8px;}
.primary-btn:hover { background: var(--accent-hover); }
.secondary-btn { background: var(--btn-secondary); color: var(--text-main); border: none; padding: 14px 28px; border-radius: 980px; font-size: 1.05rem; font-weight: 500; cursor: pointer; transition: background 0.2s; display: inline-flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none;}
.secondary-btn:hover { background: var(--btn-secondary-hover); }
/* Gesperrte Knöpfe sahen bisher aus wie bedienbare und färbten sich beim
   Darüberfahren sogar noch ein. Wer während einer laufenden Aktion darauf
   klickte, bekam keinerlei Rückmeldung. */
button:disabled, .primary-btn:disabled, .secondary-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.primary-btn:disabled:hover { background: var(--accent-color); }
.secondary-btn:disabled:hover { background: var(--btn-secondary); }

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
.main-card-img { width: 100%; max-width: 420px; aspect-ratio: 63 / 88; object-fit: cover; background: var(--btn-secondary); border-radius: 4.75% / 3.5%; box-shadow: 0 25px 60px rgba(0,0,0,0.3); margin-bottom: 25px; display: block; }
.prints-scroll { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 15px; scrollbar-width: thin; }
/* aspect-ratio + Hintergrund reservieren Platz, damit die Editionen-Leiste
   während des Ladens nicht auf 0 Höhe kollabiert (wirkte sonst "leer"). */
.print-thumb { width: 80px; aspect-ratio: 63 / 88; object-fit: cover; background: var(--btn-secondary); flex-shrink: 0; border-radius: 4.75% / 3.5%; cursor: pointer; opacity: 0.55; transition: all 0.2s; box-shadow: 0 4px 10px rgba(0,0,0,0.2); border: 2px solid transparent; }
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
.split-editor-text { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 30px; }
.split-editor-visual { display: grid; grid-template-columns: 400px 1fr; gap: 30px; }
@media (max-width: 1100px) {
  .split-editor-container, .split-editor-text, .split-editor-visual { grid-template-columns: 1fr !important; }
}
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
.judge-widget-btn { position: fixed; bottom: 24px; right: 24px; width: 60px; height: 60px; border-radius: 50%; background: var(--accent-color); color: var(--accent-text); border: none; box-shadow: 0 10px 30px var(--shadow-color); cursor: pointer; z-index: 10000; transition: transform 0.2s; display: flex; align-items: center; justify-content: center; }
.judge-widget-btn:hover { transform: scale(1.1); }
.judge-chat-window { position: fixed; bottom: 94px; right: 24px; width: 350px; max-width: calc(100vw - 40px); max-height: min(500px, calc(100vh - 130px)); background: var(--bg-card); border-radius: 20px; box-shadow: 0 20px 50px rgba(0,0,0,0.3); border: 1px solid var(--border-color); z-index: 10000; display: flex; flex-direction: column; overflow: hidden; animation: slideUp 0.3s ease; }
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

/* --- BENTO DASHBOARD --- */
.bento-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  margin-top: 20px;
}
@media (max-width: 1024px) {
  .bento-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 768px) {
  .bento-grid {
    grid-template-columns: 1fr;
  }
}
.bento-item {
  background: var(--bg-card);
  border-radius: 24px;
  padding: 30px;
  box-shadow: 0 8px 30px var(--shadow-color);
  border: 1px solid var(--border-color);
  transition: transform 0.3s cubic-bezier(0.25, 1, 0.5, 1), box-shadow 0.3s;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.bento-item:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 40px var(--shadow-color);
}
.bento-col-2 {
  grid-column: span 2;
}
@media (max-width: 768px) {
  .bento-col-2 {
    grid-column: span 1;
  }
}

.fade-in-img {
  opacity: 0;
  transition: opacity 0.4s ease-in-out;
}
.fade-in-img.loaded {
  opacity: 1;
}

/* ==================================================================
   ACHTUNG: Diese Datei ist die EINZIGE Quelle globaler Stile.
   src/App.css wird nirgends importiert -- Regeln dort bleiben wirkungslos.
   ================================================================== */
/* Kartentreffer im Deck-Editor: das Vorschaubild vergrössert sich beim
   Darüberfahren, damit ähnliche Karten sicher unterscheidbar sind. Zwei
   Fassungen derselben Karte waren bei Briefmarkengrösse nicht zu trennen. */
.kartentreffer-bild {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  transform-origin: left center;
}
.kartentreffer-bild:hover {
  transform: scale(3.2);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
  position: relative;
  z-index: 20;
}
@media (prefers-reduced-motion: reduce) {
  .kartentreffer-bild { transition: none; }
}

/* Textlinks, die technisch Schaltflächen sind ("Passwort vergessen?",
   "Konto erstellen"). Vorher waren das <span>-Elemente mit onClick: nicht per
   Tastatur erreichbar und für Screenreader unsichtbar. */
.link-button {
  background: none;
  border: none;
  padding: 4px;
  font: inherit;
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.link-button:hover { color: var(--text-main); }
.link-button:focus-visible {
  outline: 2px solid var(--accent-color);
  outline-offset: 2px;
  border-radius: 4px;
}

/* Einheitliches Raster für Deck- und Ordnerkacheln. Vorher 280px bei den
   Decks, 260px bei den Ordnern und 220px im Standard-Raster -- dieselbe Art
   Kachel sprang je nach Seite in der Breite. In rem statt px, damit eine
   grössere Schriftgrösse im Browser das Raster mitzieht; min(100%, …)
   verhindert das seitliche Überlaufen auf schmalen Fenstern. */
.karten-raster {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr));
  gap: 25px;
  margin-top: 20px;
}

/* ==================================================================
   Konto-Menü in der Kopfzeile (siehe components/layout/AppleHeader.jsx)
   Die sechs Farbkreise und der Hell/Dunkel-Schalter lagen dauerhaft
   zwischen den Seitenlinks. Sie sind Einstellungen und sitzen jetzt
   unter dem Benutzernamen.
   ================================================================== */
.konto-menu { position: relative; }
.konto-knopf {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: none;
  font: inherit;
  font-size: 0.9rem;
  color: var(--text-muted);
  cursor: pointer;
}
.konto-knopf:hover { color: var(--text-main); border-color: var(--border-color); }
.konto-knopf[aria-expanded="true"] {
  color: var(--text-main);
  border-color: var(--border-color);
  background: var(--btn-secondary);
}
.konto-knopf:focus-visible { outline: 2px solid var(--accent-color); outline-offset: 2px; }
.konto-kuerzel {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-color);
  color: var(--bg-main);
  font-size: 0.78rem;
  font-weight: 700;
  flex-shrink: 0;
}
.konto-name { max-width: 12rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.konto-pfeil { font-size: 0.7rem; opacity: 0.7; }

.konto-klappe {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 10000;
  width: 17rem;
  padding: 8px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: var(--bg-card);
  box-shadow: 0 12px 34px var(--shadow-color);
  text-align: left;
}
.konto-kopf {
  margin: 4px 10px 10px;
  font-size: 0.8rem;
  color: var(--text-muted);
}
.konto-kopf strong { color: var(--text-main); }
.konto-gruppe { padding: 8px 0; border-top: 1px solid var(--border-color); }
.konto-gruppe:first-of-type { border-top: none; padding-top: 0; }
.konto-titel {
  display: block;
  padding: 0 10px 6px;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.konto-eintrag {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  border-radius: 9px;
  background: none;
  font: inherit;
  font-size: 0.9rem;
  color: var(--text-main);
  text-align: left;
  cursor: pointer;
}
.konto-eintrag:hover { background: var(--btn-secondary); }
.konto-eintrag:focus-visible { outline: 2px solid var(--accent-color); outline-offset: -2px; }

.konto-farben { display: flex; flex-direction: column; }
/* Die Farbkreise tragen jetzt ihren Namen -- ein Kreis allein war nicht
   verständlich, ohne mit der Maus darauf zu warten. */
.konto-farbe {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 7px 10px;
  border: none;
  border-radius: 9px;
  background: none;
  font: inherit;
  font-size: 0.88rem;
  color: var(--text-main);
  text-align: left;
  cursor: pointer;
}
.konto-farbe:hover { background: var(--btn-secondary); }
.konto-farbe:focus-visible { outline: 2px solid var(--accent-color); outline-offset: -2px; }
.konto-farbe > img,
.konto-farbe-standard {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--border-color);
  flex-shrink: 0;
}
.konto-farbe-standard {
  background: var(--text-muted);
  color: var(--bg-card);
  font-size: 0.6rem;
  font-weight: 700;
}
.konto-farbe.aktiv { font-weight: 700; }
.konto-farbe.aktiv > img,
.konto-farbe.aktiv .konto-farbe-standard { border: 2px solid var(--accent-color); }
.konto-farbe.aktiv .konto-farbe-name::after {
  content: ' ✓';
  color: var(--accent-color);
}

/* ==================================================================
   Rückmeldungen und Rückfragen (siehe components/layout/Meldungen.jsx)
   Ersetzen die nativen alert()/confirm()-Dialoge, die die Seite
   blockierten und auf dem Handy die technische Adresse anzeigten.
   ================================================================== */
.meldungs-liste {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(30rem, calc(100vw - 32px));
  pointer-events: none;
}
/* In schmalen Fenstern reicht die Einblendung bis unter den Judge-Knopf --
   dann rutscht sie darüber, statt sich mit ihm zu überlagern. */
@media (max-width: 700px) {
  .meldungs-liste { bottom: 96px; }
}
.meldung {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 14px 13px 16px;
  border-radius: 12px;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-main);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.22);
  font-size: 0.93rem;
  line-height: 1.45;
  animation: meldung-auf 0.18s ease-out;
}
@keyframes meldung-auf {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) {
  .meldung { animation: none; }
}
/* Der farbige Streifen trägt die Bedeutung zusätzlich zur Farbe --
   allein über Farbe wäre sie für Farbenblinde nicht erkennbar, deshalb
   steht die Aussage immer auch im Text. */
.meldung::before {
  content: '';
  width: 3px;
  align-self: stretch;
  border-radius: 2px;
  flex-shrink: 0;
}
.meldung-erfolg::before { background: var(--price-color, #3C6B45); }
.meldung-fehler::before { background: var(--danger-color, #A32B22); }
.meldung-info::before   { background: var(--accent-color); }
.meldung-text { flex: 1; word-break: break-word; }
.meldung-schliessen {
  background: none; border: none; cursor: pointer;
  color: var(--text-muted); font-size: 1.2rem; line-height: 1;
  padding: 0 2px; flex-shrink: 0;
}
.meldung-schliessen:hover { color: var(--text-main); }
.meldung-schliessen:focus-visible {
  outline: 2px solid var(--accent-color); outline-offset: 2px; border-radius: 4px;
}

.rueckfrage-hintergrund {
  position: fixed; inset: 0; z-index: 100001;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.rueckfrage {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: clamp(20px, 5vw, 28px);
  width: min(26rem, 100%);
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
}
.rueckfrage-titel { font-size: 1.15rem; font-weight: 700; margin: 0 0 10px; color: var(--text-main); }
.rueckfrage-text { color: var(--text-muted); margin: 0 0 22px; line-height: 1.55; font-size: 0.95rem; }
.rueckfrage-knoepfe { display: flex; gap: 10px; justify-content: flex-end; flex-wrap: wrap; }
.gefahr-btn {
  background: var(--danger-color, #A32B22); color: #fff; border: none;
  padding: 10px 20px; border-radius: 10px; font-weight: 600; cursor: pointer;
}
.gefahr-btn:hover { filter: brightness(1.1); }
`;

function App() {
  const { melde } = useMeldung();
  const [currentUser, setCurrentUser] = useState(localStorage.getItem("username") || null);
  const [userRole, setUserRole] = useState("free");
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [isJudgeOpen, setIsJudgeOpen] = useState(false); 
  const [showPremiumModal, setShowPremiumModal] = useState(false);
  const [activeTheme, setActiveTheme] = useState(() => localStorage.getItem("active-theme") || "default");
  const navigate = useNavigate();
  const location = useLocation();

  const handleLoginSuccess = (username, token, role, refreshToken) => {
    localStorage.setItem("username", username);
    setTokens(token, refreshToken);
    setCurrentUser(username);
    setUserRole(role || "free");

    // Nach abgelaufener Sitzung dorthin zurück, wo der Nutzer war -- nicht
    // stumpf auf die Startseite. Der Merker wird dabei verbraucht.
    try {
      const zurueck = sessionStorage.getItem("nach-anmeldung");
      if (zurueck) {
        sessionStorage.removeItem("nach-anmeldung");
        navigate(zurueck, { replace: true });
      }
    } catch { /* ohne sessionStorage bleibt es bei der Startseite */ }
  };

  const handleLogout = () => {
    localStorage.removeItem("username");
    clearTokens();
    setCurrentUser(null);
    setUserRole("free");
  };

  // Wenn der Auth-Interceptor den Refresh nicht mehr durchbekommt (Refresh-
  // Token abgelaufen/ungültig), setzt er die Tokens zurück und feuert
  // "auth:logout" -- die App muss dann ihren Login-Zustand nachziehen.
  useEffect(() => {
    const onAuthLogout = () => {
      // Vorher passierte das lautlos: Der Nutzer landete mitten in der Arbeit
      // auf der Marketing-Startseite, ohne zu erfahren, warum. Jetzt gibt es
      // eine Meldung, und die zuletzt geöffnete Seite wird gemerkt, damit die
      // Anmeldung dorthin zurückführt statt auf die Startseite.
      try {
        const zurueck = window.location.pathname + window.location.search;
        if (zurueck && zurueck !== "/") sessionStorage.setItem("nach-anmeldung", zurueck);
      } catch { /* privater Modus: dann eben ohne Rücksprung */ }
      localStorage.removeItem("username");
      setCurrentUser(null);
      setUserRole("free");
      melde.fehler("Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
    };
    window.addEventListener("auth:logout", onAuthLogout);
    return () => window.removeEventListener("auth:logout", onAuthLogout);
  }, [melde]);

  useEffect(() => {
    if (isDarkMode) document.body.classList.add('dark-mode');
    else document.body.classList.remove('dark-mode');
  }, [isDarkMode]);

  useEffect(() => {
    localStorage.setItem("active-theme", activeTheme);
    const themes = ["theme-plains", "theme-island", "theme-swamp", "theme-mountain", "theme-forest"];
    themes.forEach(t => document.body.classList.remove(t));
    if (activeTheme !== "default") {
      document.body.classList.add(`theme-${activeTheme}`);
    }
  }, [activeTheme]);

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
    if (params.get('status') !== 'success') {
      return;
    }

    const user = params.get('user') || currentUser;
    const isMock = params.get('mock_upgrade') === 'true';
    const sessionId = params.get('session_id');
    let cancelled = false;

    if (isMock && user) {
      fetch('/api/user/update-role', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ benutzername: user, rolle: 'premium' })
      })
        .then(res => res.json())
        .then(data => {
          if (cancelled) return;
          if (data && data.erfolg) {
            melde.erfolg("Upgrade erfolgreich durchgeführt! (Simulation)");
            setUserRole("premium");
          }
          // Query-Parameter immer entfernen, auch bei Fehlschlag -- sonst
          // bleibt die Seite in diesem URL-Zustand hängen.
          navigate('/premium', { replace: true });
        })
        .catch(() => {
          if (!cancelled) navigate('/premium', { replace: true });
        });
      return () => { cancelled = true; };
    }

    if (sessionId && user) {
      // Stripe hat die Zahlung bestätigt, aber der Webhook, der rolle='premium'
      // setzt, kommt asynchron und mit etwas Verzögerung an. Statt die ganze
      // Seite per window.location.reload() neu zu laden (das setzt JEDEN
      // Zähler zurück und führt bei einem fehlenden/verzögerten Webhook zu
      // einer Endlosschleife aus Reloads -- genau das sichtbare "Flackern"),
      // pollen wir den Rollen-Status im Hintergrund mit einer festen
      // Obergrenze an Versuchen.
      const MAX_ATTEMPTS = 8;
      const POLL_INTERVAL_MS = 3000;
      let attempt = 0;

      const finishSuccess = () => {
        melde.erfolg("Upgrade erfolgreich durchgeführt! Vielen Dank.");
        setUserRole("premium");
        navigate('/premium', { replace: true });
      };

      // Zuerst serverseitig bei Stripe verifizieren. Das schaltet Premium sofort
      // frei -- auch ohne (bzw. vor dem) Webhook, was besonders lokal ohne
      // öffentliche Webhook-URL sonst gar nicht funktionieren würde. Der Server
      // prüft die Zahlung direkt bei Stripe; dem Client wird nichts geglaubt.
      fetch('/api/checkout/verify-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      })
        .then(res => res.json().catch(() => ({})))
        .then(data => {
          if (cancelled) return;
          if (data && data.erfolg) {
            finishSuccess();
            return;
          }
          // Noch nicht bestätigt -> als Fallback den Webhook-Status pollen.
          checkRole();
        })
        .catch(() => { if (!cancelled) checkRole(); });

      const checkRole = () => {
        fetch(`/api/user/role/${user}`)
          .then(res => res.json())
          .then(data => {
            if (cancelled) return;
            if (data && data.rolle === 'premium') {
              finishSuccess();
              return;
            }
            attempt += 1;
            if (attempt >= MAX_ATTEMPTS) {
              melde.fehler("Deine Zahlung wurde von Stripe bestätigt, aber dein Premium-Status ist " +
                "noch nicht angekommen. Das kann kurz dauern -- lade die Seite in ein bis " +
                "zwei Minuten neu. Falls es weiterhin nicht klappt, kontaktiere den Support.");
              navigate('/premium', { replace: true });
              return;
            }
            setTimeout(checkRole, POLL_INTERVAL_MS);
          })
          .catch(() => {
            if (cancelled) return;
            attempt += 1;
            if (attempt >= MAX_ATTEMPTS) {
              navigate('/premium', { replace: true });
              return;
            }
            setTimeout(checkRole, POLL_INTERVAL_MS);
          });
      };

      // checkRole() wird von der verify-session-Antwort oben als Fallback
      // gestartet -- hier bewusst KEIN direkter Aufruf, sonst würde doppelt
      // gepollt.
      return () => { cancelled = true; };
    }
  }, [location, currentUser, navigate]);

  const isCameraView = location.pathname.startsWith('/playfield/camera/');
  // Geteilte Decks sind öffentlich (read-only) und dürfen ohne Login geöffnet werden.
  const isSharedDeckView = location.pathname.startsWith('/shared/decks/');

  // Rechtsseiten sind oeffentlich: sie muessen auch ohne Anmeldung erreichbar
  // sein. Frueher landete jeder ausgeloggte Aufruf auf der Landing Page -- ein
  // Link auf /impressum haette also ins Leere gefuehrt.
  const RECHTSSEITEN = ['/impressum', '/datenschutz', '/agb', '/passwort-neu'];
  if (RECHTSSEITEN.includes(location.pathname)) {
    return (
      <>
        <style>{globalStyles}</style>
        <Routes>
          <Route path="/impressum" element={<Impressum />} />
          <Route path="/datenschutz" element={<Datenschutz />} />
          <Route path="/agb" element={<AGB />} />
          <Route path="/passwort-neu" element={<PasswortNeu />} />
        </Routes>
        <Footer />
      </>
    );
  }

  if (isSharedDeckView) {
    return (
      <>
        <style>{globalStyles}</style>
        <Routes>
          <Route path="/shared/decks/:id" element={<SharedDeckView />} />
        </Routes>
      </>
    );
  }

  if (!currentUser && !isCameraView) {
    return (
      <>
        <style>{globalStyles}</style>
        <LandingPage 
          onLoginSuccess={handleLoginSuccess} 
          activeTheme={activeTheme} 
          setActiveTheme={setActiveTheme} 
        />
        <Footer />
      </>
    );
  }
  
  return (
    <>
      <style>{globalStyles}</style>
      {!isCameraView && (
        <AppleHeader 
          currentUser={currentUser} 
          setCurrentUser={handleLogout} 
          isDarkMode={isDarkMode} 
          setIsDarkMode={setIsDarkMode} 
          setIsJudgeOpen={setIsJudgeOpen} 
          activeTheme={activeTheme}
          setActiveTheme={setActiveTheme}
        />
      )}
      <main>
        <Routes>
          <Route path="/" element={<EntdeckenHub currentUser={currentUser} userRole={userRole} onShowPremiumModal={() => setShowPremiumModal(true)} />} />
          <Route path="/sammlung" element={<MeineSammlung currentUser={currentUser} userRole={userRole} setUserRole={setUserRole} onShowPremiumModal={() => setShowPremiumModal(true)} />} />
          <Route path="/decks" element={<DecksView currentUser={currentUser} userRole={userRole} onShowPremiumModal={() => setShowPremiumModal(true)} />} />
          <Route path="/premium" element={<PremiumPage currentUser={currentUser} userRole={userRole} setUserRole={setUserRole} />} />
          {/* Live-Playfield fürs erste Launch pausiert (siehe config.js).
              Aktive Routen nur, wenn der Feature-Schalter an ist; sonst leitet
              ein direkter /playfield-Aufruf auf die Startseite um (kein toter Link). */}
          {FEATURES.livePlayfield ? (
            <>
              <Route path="/playfield" element={<PlayfieldView currentUser={currentUser} userRole={userRole} onShowPremiumModal={() => setShowPremiumModal(true)} />} />
              <Route path="/playfield/camera/:sessionId" element={<MobileCamera />} />
            </>
          ) : (
            <Route path="/playfield/*" element={<Navigate to="/" replace />} />
          )}
        </Routes>
      </main>
      {!isCameraView && <Footer />}
      {!isCameraView && (
        <>
          <JudgeWidget open={isJudgeOpen} setOpen={setIsJudgeOpen} currentUser={currentUser} userRole={userRole} onShowPremiumModal={() => setShowPremiumModal(true)} />
          <PremiumUpgradeModal isOpen={showPremiumModal} onClose={() => setShowPremiumModal(false)} />
        </>
      )}
    </>
  );
}

export default App;