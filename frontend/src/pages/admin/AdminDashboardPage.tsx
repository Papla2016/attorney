import { Link } from 'react-router-dom';
import AppLayout from '../../components/layout/AppLayout';

export default function AdminDashboardPage(){return <AppLayout><h1>Админ-панель</h1><div className='info-grid'>
<div className='card'><h3>Пользователи</h3><Link to='/admin/users' className='button'>Управление пользователями</Link></div>
<div className='card'><h3>Справочник судов</h3><Link to='/admin/courts' className='button'>Управление судами</Link></div>
<div className='card'><h3>Журнал аудита</h3><Link to='/admin/audit' className='button'>Открыть аудит</Link></div>
<div className='card'><h3>Состояние сервисов</h3><p>auth-service: запланировано</p><p>case-service: запланировано</p><p>ner-service: запланировано</p><p>anonymization-service: запланировано</p></div>
</div></AppLayout>;}
