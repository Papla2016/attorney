import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { register as reg } from '../api/authApi';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { getApiErrorMessage } from '../utils/errors';
import AppLayout from '../components/layout/AppLayout';

const schema = z.object({
  username: z.string().min(1, 'Введите логин'),
  email: z.string().email('Введите корректную почту'),
  password: z.string().min(8, 'Пароль должен быть не короче 8 символов'),
  repeatPassword: z.string().min(8, 'Пароль должен быть не короче 8 символов')
}).refine((v) => v.password === v.repeatPassword, { message: 'Пароли не совпадают', path: ['repeatPassword'] });

export default function RegisterPage() {
  const nav = useNavigate();
  const [error, setError] = useState('');
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema) });
  return <AppLayout><div className='card form-card'><h2>Регистрация</h2>{error && <p className='error-message'>{error}</p>}<form onSubmit={handleSubmit(async (v) => { try { setError(''); await reg({ username: v.username, email: v.email, password: v.password }); nav('/login', { state: { message: 'Регистрация успешна. Теперь войдите в систему.' } }); } catch (e:any) { if (e?.response?.status === 400) setError('Пользователь с таким логином уже существует или данные заполнены неверно'); else setError(getApiErrorMessage(e)); } })}>
  <label>Логин</label><input placeholder='Например: ivanov' {...register('username')} /><small>Будет использоваться для входа в систему</small>{errors.username && <p className='error-message'>{errors.username.message as string}</p>}
  <label>Электронная почта</label><input placeholder='user@example.com' {...register('email')} />{errors.email && <p className='error-message'>{errors.email.message as string}</p>}
  <label>Пароль</label><input type='password' placeholder='Минимум 8 символов' {...register('password')} />{errors.password && <p className='error-message'>{errors.password.message as string}</p>}
  <label>Повторите пароль</label><input type='password' placeholder='Введите пароль ещё раз' {...register('repeatPassword')} />{errors.repeatPassword && <p className='error-message'>{errors.repeatPassword.message as string}</p>}
  <button className='button' disabled={isSubmitting}>Зарегистрироваться</button></form><Link to='/login'>Уже есть аккаунт? Войти</Link></div></AppLayout>;
}
