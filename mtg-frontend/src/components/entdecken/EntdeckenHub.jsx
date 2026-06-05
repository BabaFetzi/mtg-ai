import { useLocation, useNavigate } from 'react-router-dom';
import Dashboard from './Dashboard';
import KartenSuche from './KartenSuche';
import MarktTrends from './MarktTrends';
import SynergieAnsicht from './SynergieAnsicht';
import JudgeChat from './JudgeChat';
import RegelbuchAnsicht from './RegelbuchAnsicht';

function EntdeckenHub({ currentUser, userRole, onShowPremiumModal }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const viewMode = queryParams.get('view') || 'dashboard';

  return (
    <div className="apple-main-container">
      <div className="segmented-control" style={{marginBottom: '30px', margin: '0 auto 40px auto', display: 'flex'}}>
        <button className={`segment-btn ${viewMode === 'dashboard' ? 'active' : ''}`} onClick={() => navigate('/?view=dashboard')}>Dashboard</button>
        <button className={`segment-btn ${viewMode === 'search' ? 'active' : ''}`} onClick={() => navigate('/?view=search')}>Kartensuche</button>
        <button className={`segment-btn ${viewMode === 'trends' ? 'active' : ''}`} onClick={() => navigate('/?view=trends')}>Markt-Trends</button>
        <button className={`segment-btn ${viewMode === 'synergy' ? 'active' : ''}`} onClick={() => navigate('/?view=synergy')}>Synergie-Scanner</button>
        <button className={`segment-btn ${viewMode === 'judge' ? 'active' : ''}`} onClick={() => navigate('/?view=judge')}>Rules Judge</button>
        <button className={`segment-btn ${viewMode === 'rulebook' ? 'active' : ''}`} onClick={() => navigate('/?view=rulebook')}>Regelbuch</button>
      </div>

      {viewMode === 'dashboard' && <Dashboard currentUser={currentUser} />}
      {viewMode === 'search' && <KartenSuche currentUser={currentUser} onShowPremiumModal={onShowPremiumModal} />}
      {viewMode === 'trends' && <MarktTrends currentUser={currentUser} />}
      {viewMode === 'synergy' && <SynergieAnsicht currentUser={currentUser} userRole={userRole} onShowPremiumModal={onShowPremiumModal} />}
      {viewMode === 'judge' && <JudgeChat currentUser={currentUser} userRole={userRole} onShowPremiumModal={onShowPremiumModal} />}
      {viewMode === 'rulebook' && <RegelbuchAnsicht />}
    </div>
  );
}

export default EntdeckenHub;
