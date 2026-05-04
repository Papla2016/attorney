import { Link } from 'react-router-dom';
import AppLayout from '../../components/layout/AppLayout';

export default function StaffDashboardPage() {
  return <AppLayout><h1>Панель работника суда</h1><p>Здесь можно создавать карточки дел, загружать судебные документы и отслеживать статус обезличивания.</p><div className='card'><div className='form-row'><Link to='/staff/cases/create'>Создать дело</Link><Link to='/staff/cases'>Мои дела</Link><Link to='/'>Поиск документов</Link><Link to='/favorites'>Избранное</Link></div></div></AppLayout>;
}
