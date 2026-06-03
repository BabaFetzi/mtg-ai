import { useLocation, useNavigate } from 'react-router-dom';
import KartenSuche from './KartenSuche';
import MarktTrends from './MarktTrends';
import SynergieAnsicht from './SynergieAnsicht';
import JudgeChat from './JudgeChat';
import RegelbuchAnsicht from './RegelbuchAnsicht';

function EntdeckenHub({ currentUser, userRole }) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryParams = new URLSearchParams(location.search);
  const viewMode = queryParams.get('view') || 'search';

  return (
    <div className="apple-main-container">
      <div className="segmented-control" style={{marginBottom: '30px', margin: '0 auto 40px auto', display: 'flex'}}>
        <button className={`segment-btn ${viewMode === 'search' ? 'active' : ''}`} onClick={() => navigate('/?view=search')}>Kartensuche</button>
        <button className={`segment-btn ${viewMode === 'trends' ? 'active' : ''}`} onClick={() => navigate('/?view=trends')}>Markt-Trends</button>
        <button className={`segment-btn ${viewMode === 'synergy' ? 'active' : ''}`} onClick={() => navigate('/?view=synergy')}>Synergie-Scanner</button>
        <button className={`segment-btn ${viewMode === 'judge' ? 'active' : ''}`} onClick={() => navigate('/?view=judge')}>KI-Judge</button>
        <button className={`segment-btn ${viewMode === 'rulebook' ? 'active' : ''}`} onClick={() => navigate('/?view=rulebook')}>Regelbuch</button>
      </div>

      {viewMode === 'search' && <KartenSuche currentUser={currentUser} />}
      {viewMode === 'trends' && <MarktTrends />}
      {viewMode === 'synergy' && <SynergieAnsicht currentUser={currentUser} userRole={userRole} />}
      {viewMode === 'judge' && <JudgeChat currentUser={currentUser} userRole={userRole} />}
      {viewMode === 'rulebook' && <RegelbuchAnsicht />}
    </div>
  );
}

export default EntdeckenHub;
