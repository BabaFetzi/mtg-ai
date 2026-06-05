import React from 'react';

// CSS animation added globally or inline
const pulseStyles = `
@keyframes skeletonPulse {
  0% { opacity: 0.6; }
  50% { opacity: 1; }
  100% { opacity: 0.6; }
}
.skeleton-pulse {
  animation: skeletonPulse 1.5s ease-in-out infinite;
  background: var(--btn-secondary);
}
`;

export default function SkeletonLoader({ type = 'card', count = 1, style = {} }) {
  const items = Array.from({ length: count });

  return (
    <>
      <style>{pulseStyles}</style>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px', width: '100%', ...style }}>
        {type === 'card' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '30px', width: '100%' }}>
            {items.map((_, i) => (
              <div 
                key={i} 
                className="skeleton-pulse" 
                style={{ 
                  borderRadius: '16px', 
                  aspectRatio: '2.5/3.5', 
                  width: '100%', 
                  border: '1px solid var(--border-color)' 
                }} 
              />
            ))}
          </div>
        )}

        {type === 'list' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%' }}>
            {items.map((_, i) => (
              <div 
                key={i} 
                className="skeleton-pulse" 
                style={{ 
                  height: '60px', 
                  borderRadius: '12px', 
                  width: '100%', 
                  border: '1px solid var(--border-color)' 
                }} 
              />
            ))}
          </div>
        )}

        {type === 'text' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
            {items.map((_, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%' }}>
                <div className="skeleton-pulse" style={{ height: '24px', borderRadius: '4px', width: '40%' }} />
                <div className="skeleton-pulse" style={{ height: '14px', borderRadius: '4px', width: '85%' }} />
                <div className="skeleton-pulse" style={{ height: '14px', borderRadius: '4px', width: '70%' }} />
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
