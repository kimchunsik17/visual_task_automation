import React, { useState, useEffect } from 'react';
import { AlertCircle, CheckCircle } from 'lucide-react';
import './CustomAlert.css';

const CustomAlert = () => {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    // Override window.alert
    const originalAlert = window.alert;
    window.alert = (message) => {
      const id = Date.now() + Math.random();
      setAlerts(prev => [...prev, { id, message }]);
    };

    return () => {
      window.alert = originalAlert; // Restore on unmount
    };
  }, []);

  const closeAlert = (id) => {
    setAlerts(prev => prev.filter(alert => alert.id !== id));
  };

  if (alerts.length === 0) return null;

  // We'll just render the first one or stack them, let's stack them visually or just render all with overlay
  return (
    <div className="custom-alert-overlay">
      {alerts.map((alert, index) => (
        <div key={alert.id} className="custom-alert-modal" style={{ zIndex: 10000 + index }}>
          <div className="custom-alert-icon">
            {alert.message.includes('실패') || alert.message.includes('오류') ? (
              <AlertCircle size={32} color="#f87171" />
            ) : (
              <CheckCircle size={32} color="#34d399" />
            )}
          </div>
          <div className="custom-alert-content">
            <p className="custom-alert-message">{alert.message}</p>
            <button className="custom-alert-button" onClick={() => closeAlert(alert.id)}>
              확인
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default CustomAlert;
