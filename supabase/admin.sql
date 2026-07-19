insert into admins (admin_name, email, password_hash)
values (
  'Your Name',
  'you@example.com',
  crypt('a-strong-password-here', gen_salt('bf'))
);