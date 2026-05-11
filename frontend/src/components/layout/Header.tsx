import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/useAuth';
import { isAdmin, isStaff } from '../../utils/roles';

export default function Header() {
  const { isAuthenticated, user, roles, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = () => {
    logout();
    navigate('/');
  };

  return (
    <header className="header">
      <div className="container header-inner">
        <Link to="/" className="brand">Судебные документы</Link>
        <nav className="nav">
          <Link to="/">Главная</Link>
          {!isAuthenticated ? (
            <>
              <Link to="/login">Войти</Link>
              <Link to="/register">Регистрация</Link>
            </>
          ) : (
            <>
              <span className="user-name">{user?.username}</span>
              <Link to="/account">Аккаунт</Link>
              <Link to="/favorites">Избранное</Link>
              <Link to={isStaff(roles) ? "/staff/cases" : "/my-cases"}>Мои дела</Link>
              {isStaff(roles) && <Link to="/staff">Панель работника суда</Link>}
              {isAdmin(roles) && <Link to="/admin">Админка</Link>}
              <button className="button button-secondary" type="button" onClick={onLogout}>Выйти</button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
