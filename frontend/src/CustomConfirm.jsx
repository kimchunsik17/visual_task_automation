import React, { useState, useEffect } from 'react';
import { Icon } from './icons';
import './CustomAlert.css';

let requestConfirm = null;

export const customConfirm = (message) => {
  if (!requestConfirm) return Promise.resolve(window.confirm(message));
  return requestConfirm(message);
};

const CustomConfirm = () => {
  const [state, setState] = useState(null); // { message, resolve }

  useEffect(() => {
    requestConfirm = (message) => new Promise((resolve) => {
      setState({ message, resolve });
    });
    return () => { requestConfirm = null; };
  }, []);

  const respond = (result) => {
    state?.resolve(result);
    setState(null);
  };

  if (!state) return null;

  return (
    <div className="custom-alert-overlay">
      <div className="custom-alert-modal">
        <div className="custom-alert-icon">
          <Icon name="status-warning" size={32} color="#fbbf24" />
        </div>
        <div className="custom-alert-content">
          <p className="custom-alert-message">{state.message}</p>
          <div className="custom-confirm-buttons">
            <button className="custom-alert-button custom-confirm-cancel" onClick={() => respond(false)}>
              취소
            </button>
            <button className="custom-alert-button custom-confirm-ok" onClick={() => respond(true)}>
              확인
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CustomConfirm;
