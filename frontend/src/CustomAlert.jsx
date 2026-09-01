import React, { useState, useEffect } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';
import './CustomAlert.css';

// 호출부가 종류를 명시하지 않은 옛 alert 들을 위한 추정 — 실패 문구가 초록 체크로
// 나가는 것만은 막는다. 새 코드는 alert(msg, 'error'|'warning'|'success') 로 명시할 것.
const guessType = (message) => {
  const msg = String(message);
  if (['실패', '오류', '에러', '못했습니다', 'Failed', 'Error'].some(w => msg.includes(w))) return 'error';
  return 'success';
};

const ICONS = {
  error: <AlertCircle size={32} color="#f87171" />,
  warning: <AlertTriangle size={32} color="#fbbf24" />,
  success: <CheckCircle size={32} color="#34d399" />,
};

const CustomAlert = () => {
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    // Override window.alert — 두 번째 인자로 종류를 받는다(네이티브 alert 는 무시하므로 안전).
    const originalAlert = window.alert;
    window.alert = (message, type) => {
      const id = Date.now() + Math.random();
      setAlerts(prev => [...prev, { id, message, type }]);
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
            {ICONS[alert.type] || ICONS[guessType(alert.message)]}
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
