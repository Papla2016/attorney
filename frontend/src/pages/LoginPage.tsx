import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../auth/useAuth';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { getApiErrorMessage } from '../utils/errors';
import { useState } from 'react';
import { isStaff } from '../utils/roles';
import AppLayout from '../components/layout/AppLayout';

const schema = z.object({ username: z.string().min(1, 'Введите логин'), password: z.string().min(1, 'Введите пароль') });

export default function LoginPage() {
  const { login, roles } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [error, setError] = useState('');
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema) });

  return <AppLayout><div className='card form-card'><h2>Вход</h2>{location.state?.message && <p className='success-message'>{location.state.message}</p>}{error && <p className='error-message'>{error}</p>}<form onSubmit={handleSubmit(async (v) => {setError(''); try { await login(v.username, v.password); nav(isStaff(roles) ? '/staff' : '/'); } catch (e:any) { const status=e?.response?.status; if(status===403) setError('Доступ запрещён'); else setError(getApiErrorMessage(e, 'login')); } })}>
    <label>Логин</label><input placeholder='Введите логин' {...register('username')} />{errors.username && <p className='error-message'>{errors.username.message as string}</p>}
    <label>Пароль</label><input type='password' placeholder='Введите пароль' {...register('password')} />{errors.password && <p className='error-message'>{errors.password.message as string}</p>}
    <button className='button' disabled={isSubmitting}>Войти</button></form><Link to='/register'>Нет аккаунта? Зарегистрироваться</Link></div></AppLayout>;
}
