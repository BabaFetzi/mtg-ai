import { useState, useEffect } from 'react';

function RegelbuchAnsicht() {
  const [ruleSearch, setRuleSearch] = useState("");
  // Offizielle Comprehensive Rules (~2700 Regeln) -- serverseitig durchsucht.
  // Die kuratierte deutsche Liste unten bleibt als Schnelleinstieg erhalten.
  const [offizielle, setOffizielle] = useState([]);
  const [ladeOffizielle, setLadeOffizielle] = useState(false);
  const [regelHinweis, setRegelHinweis] = useState("");

  useEffect(() => {
    const begriff = ruleSearch.trim();
    if (begriff.length < 3) { setOffizielle([]); setRegelHinweis(""); return; }
    let abgebrochen = false;
    setLadeOffizielle(true);
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/regeln/suchen?q=${encodeURIComponent(begriff)}&limit=20`);
        const data = await res.json().catch(() => ({}));
        if (abgebrochen) return;
        setOffizielle(Array.isArray(data.regeln) ? data.regeln : []);
        setRegelHinweis(data.hinweis || "");
      } catch {
        if (!abgebrochen) { setOffizielle([]); setRegelHinweis("Die offiziellen Regeln sind momentan nicht erreichbar."); }
      } finally {
        if (!abgebrochen) setLadeOffizielle(false);
      }
    }, 400);
    return () => { abgebrochen = true; clearTimeout(timer); setLadeOffizielle(false); };
  }, [ruleSearch]);

  
  const rulesDatabase = [
    { id: "101.1", title: "Die Goldene Regel (The Golden Rule)", text: "Wann immer der Text einer Karte einer Regel widerspricht, hat der Text der Karte Vorrang. Die Karte modifiziert die Regel für diese konkrete Situation." },
    { id: "117.1", title: "Priorität (Priority)", text: "Spieler können Zaubersprüche und Fähigkeiten nur wirken oder aktivieren, wenn sie Priorität haben. Ein Spieler erhält Priorität, nachdem ein Zauberspruch oder eine Fähigkeit verrechnet wurde, oder zu Beginn jedes Segments/jeder Phase (außer Untap und Cleanup)." },
    { id: "117.3c", title: "Priorität abgeben", text: "Wenn ein Spieler Priorität hat und nichts tun möchte, gibt er die Priorität ab. Wenn alle Spieler nacheinander Priorität abgeben, wird das oberste Objekt auf dem Stapel verrechnet. Ist der Stapel leer, endet das Segment/die Phase." },
    { id: "400.7", title: "Zonenwechsel (Zone Changes)", text: "Ein Objekt, das von einer Zone in eine andere wechselt, wird zu einem völlig neuen Objekt. Es hat keine Erinnerung an seine vorherige Existenz in der alten Zone." },
    { id: "506.1", title: "Die Kampfphase (Combat Phase)", text: "Die Kampfphase besteht aus fünf Segmenten, in dieser Reihenfolge: Beginn des Kampfes, Angreifer deklarieren, Blocker deklarieren, Kampfschaden und Ende des Kampfes." },
    { id: "508.1", title: "Angreifer deklarieren", text: "Der aktive Spieler wählt, welche seiner Kreaturen angreifen. Das Tappen dieser Kreaturen ist Teil der Deklaration. Danach erhalten Spieler Priorität, um Spontanzauber zu wirken." },
    { id: "509.1", title: "Blocker deklarieren", text: "Der verteidigende Spieler wählt, welche Kreaturen er zum Blocken einsetzt. Wird ein Angreifer geblockt, bleibt er für den Rest des Kampfes 'geblockt', selbst wenn der Blocker das Spiel verlässt." },
    { id: "608.2b", title: "Verrechnung von Sprüchen (Targets)", text: "Wenn ein Zauberspruch oder eine Fähigkeit Ziele (Targets) benötigt, wird bei der Verrechnung geprüft, ob sie noch legal sind. Sind alle Ziele illegal geworden, verpufft der Spruch ergebnislos ('fizzles')." },
    { id: "702.2", title: "Todesberührung (Deathtouch)", text: "Jeder Schaden ungleich null, der von einer Quelle mit Todesberührung einer Kreatur zugefügt wird, ist tödlicher Schaden, ungeachtet der Widerstandskraft der Kreatur." },
    { id: "702.4", title: "Doppelschlag (Double Strike)", text: "Kreaturen mit Doppelschlag fügen ihren Kampfschaden in einem zusätzlichen, vorgezogenen Kampfschadens-Segment zu (gleichzeitig mit Erstschlag), und dann noch einmal im regulären Kampfschadens-Segment." },
    { id: "702.19", title: "Trampelschaden (Trample)", text: "Überschüssiger Kampfschaden einer angreifenden Kreatur mit Trampelschaden, der nicht benötigt wird, um alle ihre Blocker tödlich zu verletzen, kann stattdessen dem verteidigenden Spieler oder Planeswalker zugefügt werden." },
    { id: "702.11", title: "Fluchsicher (Hexproof)", text: "Ein permanent oder Spieler mit Fluchsicher kann nicht das Ziel von Zaubersprüchen oder Fähigkeiten sein, die von einem Gegner kontrolliert werden." },
    { id: "702.12", title: "Unzerstörbar (Indestructible)", text: "Kreaturen mit Unzerstörbar können nicht durch 'Zerstöre'-Effekte (Destroy) oder tödlichen Schaden auf den Friedhof gelegt werden. Sie können aber ins Exil geschickt (Exile) oder geopfert (Sacrifice) werden." },
    { id: "704.5f", title: "State-Based Actions (Toughness 0)", text: "Wenn die Widerstandskraft (Toughness) einer Kreatur 0 oder weniger beträgt, wird sie auf den Friedhof ihres Besitzers gelegt. Dies ist kein 'Zerstören' und umgeht Unzerstörbar." }
  ];

  const filteredRules = rulesDatabase.filter(r => 
    r.title.toLowerCase().includes(ruleSearch.toLowerCase()) || 
    r.text.toLowerCase().includes(ruleSearch.toLowerCase()) ||
    r.id.includes(ruleSearch)
  );

  return (
    <div style={{maxWidth: '1000px', margin: '0 auto'}}>
      <div className="search-hero" style={{paddingTop: '0'}}>
        <h2>Regel-Nachschlagewerk.</h2>
        <p>
          {rulesDatabase.length} Grundregeln auf Deutsch für den Spielalltag – dazu die
          vollständigen offiziellen Comprehensive Rules von Wizards of the Coast
          (im Original auf Englisch), durchsuchbar über das Suchfeld.
        </p>
      </div>

      <div className="content-card" style={{padding: '40px'}}>
        <input
          type="text"
          placeholder="Alle offiziellen Regeln durchsuchen (z.B. 'Todesberührung', 'Trampelschaden', '704.5f')..."
          value={ruleSearch}
          onChange={(e) => setRuleSearch(e.target.value)}
          style={{marginBottom: '30px', background: 'var(--btn-secondary)', border: 'none', boxShadow: 'none'}}
        />

        {/* Kuratierte deutsche Grundregeln */}
        {filteredRules.length > 0 && (
          <div style={{marginBottom: offizielle.length || ladeOffizielle ? '40px' : 0}}>
            <h3 style={{fontSize: '1.05rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px'}}>
              Grundregeln auf Deutsch
            </h3>
            {filteredRules.map((rule, i) => (
              <div key={i} className="rule-card">
                <h4><span className="rule-id">{rule.id}</span> {rule.title}</h4>
                <p>{rule.text}</p>
              </div>
            ))}
          </div>
        )}

        {/* Offizielle Comprehensive Rules */}
        {ruleSearch.trim().length >= 3 && (
          <div>
            <h3 style={{fontSize: '1.05rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '16px'}}>
              Offizielle Comprehensive Rules
            </h3>
            {ladeOffizielle ? (
              <div style={{textAlign: 'center', padding: '30px'}}><div className="spinner"></div></div>
            ) : offizielle.length > 0 ? (
              offizielle.map((rule) => (
                <div key={rule.nummer} className="rule-card">
                  <h4><span className="rule-id">{rule.nummer}</span></h4>
                  <p>{rule.text}</p>
                </div>
              ))
            ) : (
              <p style={{color: 'var(--text-muted)'}}>
                {regelHinweis || 'Keine offizielle Regel zu diesem Begriff gefunden.'}
              </p>
            )}
          </div>
        )}

        {ruleSearch.trim().length > 0 && ruleSearch.trim().length < 3 && (
          <p style={{color: 'var(--text-muted)'}}>Gib mindestens drei Zeichen ein, um die offiziellen Regeln zu durchsuchen.</p>
        )}
      </div>
    </div>
  );
}

export default RegelbuchAnsicht;
