import { useState } from 'react';

function RegelbuchAnsicht() {
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
    { id: "702.14.", title: "Fluchsicher (Hexproof)", text: "Ein permanent oder Spieler mit Fluchsicher kann nicht das Ziel von Zaubersprüchen oder Fähigkeiten sein, die von einem Gegner kontrolliert werden." },
    { id: "702.16.", title: "Unzerstörbar (Indestructible)", text: "Kreaturen mit Unzerstörbar können nicht durch 'Zerstöre'-Effekte (Destroy) oder tödlichen Schaden auf den Friedhof gelegt werden. Sie können aber ins Exil geschickt (Exile) oder geopfert (Sacrifice) werden." },
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
          Eine kuratierte Auswahl der {rulesDatabase.length} wichtigsten Regeln und Keywords
          für den Spielalltag – kein Ersatz für die vollständigen offiziellen Comprehensive
          Rules von Wizards of the Coast.
        </p>
      </div>

      <div className="content-card" style={{padding: '40px'}}>
        <input
          type="text"
          placeholder={`${rulesDatabase.length} kuratierte Regeln durchsuchen (z.B. 'Kampfphase', '702.1')...`}
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
    </div>
  );
}

export default RegelbuchAnsicht;
