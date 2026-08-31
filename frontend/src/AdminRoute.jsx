import { Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

function AdminRoute({ children }) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/" replace />;
  }

  if (!user.is_admin) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-color)' }}>
        <h2>Unauthorized</h2>
        <p>You do not have permission to access the admin page.</p>
        <button
          onClick={() => window.location.href = '/'}
          style={{
            marginTop: '1rem',
            padding: '0.5rem 1rem',
            background: 'var(--primary-color)',
            border: 'none',
            borderRadius: '4px',
            color: 'white',
            cursor: 'pointer'
          }}
        >
          Return Home
        </button>
      </div>
    );
  }

  return children;
}

export default AdminRoute;
