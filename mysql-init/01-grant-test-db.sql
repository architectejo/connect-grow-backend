-- Django crée une base test_<DB_NAME> pour lancer les tests (manage.py test).
-- L'utilisateur applicatif doit donc aussi pouvoir créer/détruire ces bases de test.
GRANT ALL PRIVILEGES ON `test_%`.* TO 'connecteplus'@'%';
FLUSH PRIVILEGES;
