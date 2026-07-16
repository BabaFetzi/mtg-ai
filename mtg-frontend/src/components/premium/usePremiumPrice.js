import { useEffect, useState } from 'react';

/**
 * Fragt den echten Abo-Preis vom Backend ab (/api/checkout/price), das ihn
 * live von Stripe holt. Kein fest einprogrammierter Preis mehr im Frontend --
 * ändert sich der Preis in Stripe, stimmt die Anzeige automatisch wieder,
 * ohne dass jemand den Frontend-Code anfassen muss.
 */
function formatPreis(betrag, waehrung) {
  const formatiert = betrag.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${formatiert} ${waehrung}`;
}

export default function usePremiumPrice() {
  const [preisText, setPreisText] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    fetch('/api/checkout/price')
      .then((res) => res.json())
      .then((data) => {
        if (!isMounted) return;
        if (data && data.konfiguriert) {
          setPreisText(formatPreis(data.betrag, data.waehrung));
        } else {
          setPreisText(null);
        }
      })
      .catch(() => {
        if (isMounted) setPreisText(null);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return { preisText, loading };
}
