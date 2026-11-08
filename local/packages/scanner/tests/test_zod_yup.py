"""zod / yup schemas and react-hook-form register() give form field rules."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from yoriqnoma_scanner.detect import detect
from yoriqnoma_scanner.fs_guard import SafeFS
from yoriqnoma_scanner.parsers.jsx_forms import JsxFormsParser

Writer = Callable[[Path, dict[str, str]], Path]

PROJECT = {
    "package.json": '{"dependencies": {"react": "18.3.1", "zod": "3.23.8", "yup": "1.4.0"}}',
    "src/schemas.ts": """
import { z } from 'zod';
export const registerSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8).max(64),
  phone: z.string().regex(/^\\+998\\d{9}$/),
  nickname: z.string().optional(),
});
""",
    "src/Register.tsx": """
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { registerSchema } from './schemas';
export function Register() {
  const { register, handleSubmit } = useForm({ resolver: zodResolver(registerSchema) });
  const onSubmit = async (data) => { await api.post('/api/register', data); };
  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <label htmlFor="email">Email</label>
      <input id="email" type="text" {...register('email')} />
      <label htmlFor="password">Parol</label>
      <input id="password" type="password" {...register('password')} />
      <label htmlFor="phone">Telefon</label>
      <input id="phone" {...register('phone')} />
      <label htmlFor="nickname">Taxallus</label>
      <input id="nickname" {...register('nickname')} />
      <button type="submit">Yuborish</button>
    </form>
  );
}
""",
    "src/Address.jsx": """
import * as yup from 'yup';
import { Formik, Form, Field } from 'formik';
const AddressSchema = yup.object({
  city: yup.string().min(2).required(),
  zip: yup.string().matches(/^\\d{6}$/),
});
export function Address() {
  const save = async () => { await api.put('/api/address'); };
  return (
    <form onSubmit={save}>
      <input name="city" {...register('city', { required: true, maxLength: 40 })} />
      <input name="zip" />
      <button type="submit">Saqlash</button>
      <Formik validationSchema={AddressSchema} />
    </form>
  );
}
""",
}


def test_zod_and_register_rules(tmp_path: Path, write_files: Writer) -> None:
    fs = SafeFS(write_files(tmp_path, PROJECT))
    comps = JsxFormsParser().parse(detect(fs), fs).components

    fields = {f.name: f for f in comps["Register"].forms[0].fields}
    assert fields["email"].type == "email" and fields["email"].required
    assert fields["password"].rules == "min:8|max:64"
    assert fields["phone"].rules == "regex:^\\+998\\d{9}$"
    assert not fields["nickname"].required

    address = {f.name: f for f in comps["Address"].forms[0].fields}
    assert address["city"].rules == "max:40|min:2" and address["city"].required
    assert address["zip"].rules == "regex:^\\d{6}$" and not address["zip"].required
