export const getScryfallImage = (cardName) => {
  if (!cardName) return "";
  return `https://api.scryfall.com/cards/named?exact=${encodeURIComponent(cardName.trim())}&format=image`;
};

export const getFallbackCardImage = (name, type) => {
  const cleanName = (name || "Unbekannte Karte").replace(/[\"']/g, "");
  const cleanType = (type || "Karte").replace(/[\"']/g, "");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 340" width="240" height="340">
      <rect width="240" height="340" rx="14" fill="%232C2C2E" stroke="%2338383A" stroke-width="4"/>
      <rect x="12" y="12" width="216" height="316" rx="8" fill="%231C1C1E" stroke="%2348484A" stroke-width="2"/>
      <rect x="24" y="24" width="192" height="150" rx="4" fill="%233A3A3C"/>
      <text x="32" y="200" fill="%23F5F5F7" font-family="system-ui" font-size="14" font-weight="bold">${cleanName.substring(0, 20)}</text>
      <text x="32" y="225" fill="%2398989D" font-family="system-ui" font-size="11">${cleanType.substring(0, 24)}</text>
      <text x="32" y="280" fill="%2386868B" font-family="system-ui" font-size="10" font-style="italic">Bild nicht verfuegbar</text>
    </svg>
  `.trim().replace(/\n/g, '').replace(/\s+/g, ' ');
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
};
