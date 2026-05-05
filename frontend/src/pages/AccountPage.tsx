import { useState } from 'react';
import { changePassword, updateMe } from '../api/authApi';
import { useAuth } from '../auth/useAuth';
import AppLayout from '../components/layout/AppLayout';
import { getApiErrorMessage } from '../utils/errors';

export default function AccountPage() {
  const { user, refresh } = useAuth();
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [pwdErr, setPwdErr] = useState('');
  const [pwdMsg, setPwdMsg] = useState('');

  const onProfileSave = async (e:any) => { e.preventDefault(); setErr(''); setMsg(''); const fd = new FormData(e.currentTarget); try { await updateMe({ username: String(fd.get('username') || ''), email: String(fd.get('email') || '') }); setMsg('Данные сохранены'); await refresh(); } catch (er:any) { if ([404,405].includes(er?.response?.status)) setErr('Изменение данных аккаунта пока не реализовано на backend.'); else setErr(getApiErrorMessage(er)); } };
  const onPasswordSave = async (e:any) => { e.preventDefault(); setPwdErr(''); setPwdMsg(''); const fd = new FormData(e.currentTarget); const current=String(fd.get('current_password')||''); const next=String(fd.get('new_password')||''); const repeat=String(fd.get('repeat_password')||''); if(!current) return setPwdErr('Введите текущий пароль'); if(next.length<8) return setPwdErr('Пароль должен быть не короче 8 символов'); if(next!==repeat) return setPwdErr('Пароли не совпадают'); try { await changePassword({ current_password: current, new_password: next }); setPwdMsg('Пароль изменён'); } catch (er:any) { if ([404,405].includes(er?.response?.status)) setPwdErr('Изменение данных аккаунта пока не реализовано на backend.'); else setPwdErr(getApiErrorMessage(er)); } };

  return <AppLayout><h1>Аккаунт</h1><div className='card'><p><b>Логин:</b> {user?.username}</p><p><b>Email:</b> {user?.email || '—'}</p><p><b>Роли:</b> {user?.roles?.join(', ')}</p></div>
  <div className='card form-card'><h3>Изменение профиля</h3>{err && <p className='warning-message'>{err}</p>}{msg && <p className='success-message'>{msg}</p>}<form onSubmit={onProfileSave}><label>Новый логин</label><input name='username' defaultValue={user?.username} /><label>Новая почта</label><input name='email' defaultValue={user?.email} /><button className='button'>Сохранить данные</button></form></div>
  <div className='card form-card'><h3>Изменение пароля</h3>{pwdErr && <p className='warning-message'>{pwdErr}</p>}{pwdMsg && <p className='success-message'>{pwdMsg}</p>}<form onSubmit={onPasswordSave}><label>Текущий пароль</label><input name='current_password' type='password' /><label>Новый пароль</label><input name='new_password' type='password' /><label>Повторите новый пароль</label><input name='repeat_password' type='password' /><button className='button'>Изменить пароль</button></form></div></AppLayout>;
}
