import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuth } from '../auth/useAuth';
import { useNavigate, Link } from 'react-router-dom';
const schema = z.object({username:z.string().min(1), password:z.string().min(1)});
export default function LoginPage(){ const {login}=useAuth(); const nav=useNavigate(); const {register,handleSubmit,formState:{errors}}=useForm({resolver:zodResolver(schema)});
return <form onSubmit={handleSubmit(async(v)=>{await login(v.username,v.password); nav('/');})}><h2>Вход</h2><input placeholder='username' {...register('username')}/><input type='password' placeholder='password' {...register('password')}/><button>Войти</button><p>{errors.username?.message as string}</p><Link to='/register'>Регистрация</Link></form>; }
