import { useState, useRef } from 'react';
import Icons from '../../utils/Icons';

function CSVImportExport({ currentUser, ladeSammlung }) {
  const [dragActive, setDragActive] = useState(false);
  const [file, setFile] = useState(null);
  const [previewRows, setPreviewRows] = useState([]);
  const [albumName, setAlbumName] = useState("Importierter Ordner");
  const [importStatus, setImportStatus] = useState("idle"); // "idle" | "importing" | "success" | "error"
  const [progress, setProgress] = useState(0);
  const [importResult, setImportResult] = useState(null);
  const fileInputRef = useRef(null);

  // 1. Drag & Drop Handlers
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const parseCSVPreview = (fileObject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target.result;
      const lines = text.split('\n');
      const preview = [];
      // Take first 10 lines
      for (let i = 0; i < Math.min(lines.length, 11); i++) {
        if (lines[i].trim()) {
          const cells = lines[i].split(/[,;]/).map(c => c.replace(/^["']|["']$/g, '').trim());
          preview.push(cells);
        }
      }
      setPreviewRows(preview);
    };
    reader.readAsText(fileObject);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      setFile(droppedFile);
      parseCSVPreview(droppedFile);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      parseCSVPreview(selectedFile);
    }
  };

  const handleButtonClick = () => {
    fileInputRef.current.click();
  };

  // 2. CSV Import action
  const handleImport = async () => {
    if (!file) return alert("Bitte wähle zuerst eine Datei aus.");
    setImportStatus("importing");
    setProgress(10);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("benutzername", currentUser);
    formData.append("album_name", albumName);

    try {
      setProgress(30);
      const res = await fetch("/api/sammlung/import-csv", {
        method: "POST",
        body: formData
      });
      const data = await res.json();

      if (data && data.erfolg && data.job_id) {
        setProgress(50);
        const jobId = data.job_id;
        let attempts = 0;
        
        const checkStatus = async () => {
          try {
            attempts++;
            const statusRes = await fetch(`/api/sammlung/import-status/${jobId}`);
            const statusData = await statusRes.json();
            
            if (statusData.status === "completed") {
              setProgress(100);
              setImportStatus("success");
              setImportResult({
                imported: statusData.result?.imported || 0,
                failed: statusData.result?.failed || 0,
                errors: statusData.result?.errors || []
              });
              ladeSammlung();
            } else if (statusData.status === "failed") {
              setImportStatus("error");
              alert(statusData.error || "Fehler beim Importieren der CSV.");
            } else {
              // Still processing, schedule next poll
              setProgress(Math.min(50 + attempts * 5, 95));
              setTimeout(checkStatus, 1500);
            }
          } catch (e) {
            setImportStatus("error");
            alert("Fehler beim Abrufen des Import-Status.");
          }
        };
        
        setTimeout(checkStatus, 1500);
      } else {
        setImportStatus("error");
        alert(data.error || "Fehler beim Starten des CSV-Imports.");
      }
    } catch (e) {
      setImportStatus("error");
      alert("Netzwerkfehler beim CSV-Import.");
    }
  };

  // 3. CSV Export action (Triggers FastAPI /api/sammlung/{benutzername}/export-csv endpoint)
  const handleExport = () => {
    window.location.href = `/api/sammlung/${currentUser}/export-csv`;
  };

  // 4. Download template CSV file
  const downloadTemplate = () => {
    const templateContent = "Kartenname,Anzahl,Edition,Album\nSol Ring,1,C21,Commander Staples\nLightning Bolt,4,A25,Burn Deck\n";
    const blob = new Blob([templateContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "mtg_sammlung_template.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '40px', alignItems: 'start' }}>
      {/* Import Section */}
      <div className="content-card" style={{ padding: '40px', margin: 0 }}>
        <h3 style={{ fontSize: '1.8rem', marginBottom: '10px' }}>CSV Massen-Import</h3>
        <p style={{ marginBottom: '25px' }}>Lade deine Sammlung via CSV hoch. Die Spalten müssen folgende Struktur haben: <strong>Kartenname, Anzahl, Edition, Album</strong>.</p>

        {importStatus === "idle" && (
          <>
            {/* Drag & Drop Area */}
            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              onClick={handleButtonClick}
              style={{
                border: dragActive ? '2px solid #0071E3' : '2px dashed var(--border-color)',
                background: dragActive ? 'rgba(0,113,227,0.05)' : 'var(--bg-main)',
                borderRadius: '16px',
                padding: '40px 20px',
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'all 0.2s',
                marginBottom: '25px'
              }}
            >
              <div style={{ fontSize: '3rem', marginBottom: '15px' }}>📁</div>
              <p style={{ fontWeight: 600, color: 'var(--text-main)', margin: '0 0 5px 0' }}>
                CSV-Datei hierher ziehen oder klicken
              </p>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>
                Dateiformat: .csv (maximal 10MB)
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>

            {file && (
              <div style={{ marginBottom: '25px' }}>
                <div style={{
                  background: 'var(--btn-secondary)',
                  padding: '12px 20px',
                  borderRadius: '10px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '15px'
                }}>
                  <span style={{ fontWeight: 600 }}>Ausgewählt: {file.name}</span>
                  <button onClick={() => { setFile(null); setPreviewRows([]); }} style={{ background: 'none', border: 'none', color: 'var(--danger-color)', cursor: 'pointer', fontWeight: 600 }}>Entfernen</button>
                </div>

                {/* Album select/text */}
                <div style={{ marginBottom: '20px' }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '8px' }}>Standardordner für importierte Karten</label>
                  <input
                    type="text"
                    value={albumName}
                    onChange={e => setAlbumName(e.target.value)}
                    style={{ background: 'var(--bg-main)' }}
                    placeholder="z.B. Importierter Ordner"
                  />
                </div>

                <button className="primary-btn" onClick={handleImport} style={{ width: '100%', padding: '16px' }}>Import starten</button>
              </div>
            )}
          </>
        )}

        {importStatus === "importing" && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <div className="spinner" style={{ marginBottom: '20px' }}></div>
            <h4 style={{ margin: '0 0 10px 0' }}>Import läuft...</h4>
            <p style={{ color: 'var(--text-muted)' }}>Wir prüfen deine Karten gegen die Scryfall-Datenbank.</p>
            {/* Progress Bar */}
            <div style={{ width: '100%', height: '8px', background: 'var(--btn-secondary)', borderRadius: '4px', overflow: 'hidden', marginTop: '20px' }}>
              <div style={{ width: `${progress}%`, height: '100%', background: 'var(--accent-color)', transition: 'width 0.4s' }}></div>
            </div>
          </div>
        )}

        {importStatus === "success" && importResult && (
          <div>
            <div style={{
              background: 'rgba(48, 209, 88, 0.08)',
              border: '1px solid #30D158',
              padding: '20px',
              borderRadius: '16px',
              textAlign: 'center',
              marginBottom: '25px'
            }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '10px' }}>✅</div>
              <h4 style={{ margin: '0 0 5px 0', color: 'var(--text-main)' }}>Import erfolgreich!</h4>
              <p style={{ margin: 0, color: 'var(--text-muted)' }}>
                Es wurden <strong>{importResult.imported}</strong> Karten importiert. ({importResult.failed} fehlgeschlagen)
              </p>
            </div>

            {importResult.errors.length > 0 && (
              <div style={{
                maxHeight: '180px',
                overflowY: 'auto',
                background: 'rgba(255, 69, 58, 0.05)',
                border: '1px solid var(--danger-color)',
                borderRadius: '12px',
                padding: '15px'
              }}>
                <h5 style={{ margin: '0 0 10px 0', color: 'var(--danger-color)' }}>Nicht importierte Zeilen:</h5>
                <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '0.88rem', lineHeight: '1.5', color: 'var(--text-muted)' }}>
                  {importResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                </ul>
              </div>
            )}

            <button className="secondary-btn" onClick={() => setImportStatus("idle")} style={{ width: '100%', marginTop: '20px' }}>Weiteren Import starten</button>
          </div>
        )}

        {importStatus === "error" && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <div style={{ fontSize: '3rem', marginBottom: '15px' }}>❌</div>
            <h4>Import fehlgeschlagen</h4>
            <p style={{ color: 'var(--text-muted)' }}>Es gab einen Fehler bei der Übertragung.</p>
            <button className="secondary-btn" onClick={() => setImportStatus("idle")} style={{ marginTop: '20px' }}>Erneut versuchen</button>
          </div>
        )}
      </div>

      {/* Preview / Template download column */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '25px' }}>
        {/* Template download */}
        <div className="content-card" style={{ padding: '30px', margin: 0 }}>
          <h4 style={{ margin: '0 0 10px 0' }}>Format-Template</h4>
          <p style={{ fontSize: '0.9rem', marginBottom: '20px' }}>Lade dir das Standard-Template herunter, um sicherzustellen, dass dein Import reibungslos funktioniert.</p>
          <button className="secondary-btn" onClick={downloadTemplate} style={{ width: '100%', fontSize: '0.9rem' }}>
            Template herunterladen
          </button>
        </div>

        {/* Export Button */}
        <div className="content-card" style={{ padding: '30px', margin: 0, textAlign: 'center' }}>
          <h4 style={{ margin: '0 0 10px 0' }}>Sammlung exportieren</h4>
          <p style={{ fontSize: '0.9rem', marginBottom: '20px' }}>Exportiere deine gesamte Sammlung als verifizierte CSV-Datei mit aktuellen Marktwerten.</p>
          <button className="primary-btn" onClick={handleExport} style={{ width: '100%', fontSize: '0.95rem' }}>
            <Icons.ExternalLink /> Jetzt Exportieren
          </button>
        </div>

        {/* Live Preview of parsing */}
        {previewRows.length > 0 && (
          <div className="content-card" style={{ padding: '25px', margin: 0, overflowX: 'auto' }}>
            <h4 style={{ margin: '0 0 12px 0', fontSize: '0.95rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Dateivorschau (Erste 10 Zeilen)</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                  {previewRows[0].map((cell, idx) => <th key={idx} style={{ padding: '6px', fontWeight: 600 }}>{cell}</th>)}
                </tr>
              </thead>
              <tbody>
                {previewRows.slice(1).map((row, rowIdx) => (
                  <tr key={rowIdx} style={{ borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
                    {row.map((cell, cellIdx) => <td key={cellIdx} style={{ padding: '6px', color: 'var(--text-muted)' }}>{cell}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default CSVImportExport;
