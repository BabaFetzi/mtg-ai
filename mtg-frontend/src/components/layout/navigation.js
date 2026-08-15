import { FEATURES } from '../../config';

/**
 * Die Navigation als Daten -- eine Quelle für beide Darstellungen.
 *
 * Vorher standen die Unterpunkte nur im aufklappbaren Menü der Kopfzeile, das
 * sich ausschliesslich beim Darüberfahren mit der Maus öffnete. Auf dem Handy
 * gibt es kein "Darüberfahren": Kartensuche, Trends, Synergie-Analyse, Judge,
 * Regelbuch, Wunschliste, CSV-Import und Proxy-Druck waren dort schlicht nicht
 * erreichbar. Die Handy-Navigation baut jetzt aus derselben Liste eine
 * ausklappbare Ansicht -- damit können die beiden nicht auseinanderlaufen.
 */
export function bereiche() {
  return [
    {
      id: 'suche',
      label: 'Suche & Analyse',
      pfad: '/',
      gruppen: [
        {
          titel: 'Entdecken',
          links: [
            { label: 'Kartensuche', pfad: '/?view=search' },
            { label: 'Beliebte Karten (Trends)', pfad: '/?view=trends' },
            { label: 'Marktplatz (Cardmarket)', href: 'https://www.cardmarket.com/de/Magic', extern: true },
          ],
        },
        {
          titel: 'Regeln & Analyse',
          links: [
            { label: 'Synergie-Analyse', pfad: '/?view=synergy' },
            { label: 'MTG Rules Judge', pfad: '/?view=judge' },
            { label: 'Offizielles Regelbuch', pfad: '/?view=rulebook' },
          ],
        },
      ],
    },
    {
      id: 'sammlung',
      label: 'Sammlung',
      pfad: '/sammlung?tab=alben',
      gruppen: [
        {
          titel: 'Portfolio',
          links: [
            { label: 'Ordner-Übersicht', pfad: '/sammlung?tab=alben' },
            { label: 'Neuen Ordner anlegen', pfad: '/sammlung?tab=alben&focus=neu' },
            { label: 'Marktwert & Finanzen', pfad: '/sammlung?tab=dashboard' },
          ],
        },
        {
          titel: 'Organisation',
          links: [
            { label: 'Wunschliste', pfad: '/sammlung?tab=wishlist' },
            { label: 'In- und Export (CSV)', pfad: '/sammlung?tab=import' },
          ],
        },
      ],
    },
    {
      id: 'decks',
      label: 'Decks',
      pfad: '/decks',
      gruppen: [
        {
          titel: 'Deck-Verwaltung',
          links: [
            { label: 'Meine Decks', pfad: '/decks?tab=overview' },
            { label: 'Neues Deck erstellen', pfad: '/decks?tab=overview&focus=create' },
          ],
        },
        {
          titel: 'Analyse & Werkzeuge',
          links: [
            { label: 'Deckliste & Starthand', pfad: '/decks?tab=visual' },
            { label: 'Analyse & Stats', pfad: '/decks?tab=stats' },
            ...(FEATURES.livePlayfield ? [{ label: 'Spielfeld (Live Playfield)', pfad: '/playfield' }] : []),
          ],
        },
        {
          titel: 'Export',
          links: [{ label: 'Proxy-Druck (PDF)', pfad: '/decks?tab=proxy' }],
        },
      ],
    },
  ];
}

export default bereiche;
