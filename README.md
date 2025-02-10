# Семинар 4. Docker и PostgreSQL

## Введение

Цель семинара — познакомиться с основами Docker и Docker Compose, а также научиться работать с PostgreSQL в контейнерах.

---

## 1. Запуск контейнера с PostgreSQL

1.1 Запустите контейнер с PostgreSQL:
   ```bash
   docker run -d --name pg_container -p 5432:5432 -e "POSTGRES_PASSWORD=password" postgres:latest
   ```

1.2 Проверьте, что контейнер запущен:
   ```bash
   docker ps
   ```

1.3 Зайдите в контейнер и подключитесь к PostgreSQL:
   ```bash
   docker exec -it pg_container psql -U postgres
   ```

---

## 2. Создание Dockerfile для PostgreSQL

2.1 Создайте `Dockerfile`:
   ```Dockerfile
   FROM postgres:latest
   
   ENV POSTGRES_USER=student
   ENV POSTGRES_PASSWORD=student
   ENV POSTGRES_DB=mydb
   
   EXPOSE 5432
   ```

2.2 Соберите и запустите образ:
   ```bash
   docker build -t my_postgres .
   docker run -d --name custom_pg -p 5432:5432 my_postgres
   ```

---

## 3. Работа с Docker Compose

3.1 Создайте `docker-compose.yml`:
   ```yaml
   version: '3.8'
   services:
     postgres:
       image: postgres:latest
       container_name: postgres_db
       environment:
         POSTGRES_USER: student
         POSTGRES_PASSWORD: student
         POSTGRES_DB: mydb
       ports:
         - "5432:5432"
       volumes:
         - pgdata:/var/lib/postgresql/data
       healthcheck:
         test: ["CMD-SHELL", "pg_isready -U student"]
         interval: 10s
         retries: 5
         start_period: 10s
   
   volumes:
     pgdata:
   ```

3.2 Запустите контейнеры:
   ```bash
   docker-compose up -d
   ```

3.3 Проверьте сохранность данных после перезапуска:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

---

## 4. Подключение к PostgreSQL через DataGrip

4.1 Настройте подключение:
   - Host: `localhost`
   - Port: `5432`
   - Database: `mydb`
   - User: `student`
   - Password: `student`

---

## 5. Тестовые SQL-запросы

5.1 Создайте таблицу:
   ```sql
   CREATE TABLE users (
       id SERIAL PRIMARY KEY,
       name VARCHAR(100),
       age INT
   );
   ```

5.2 Заполните таблицу:
   ```sql
   INSERT INTO users (name, age)
   SELECT md5(random()::text), floor(random() * 100)
   FROM generate_series(1, 10000);
   ```
   
   **Результат:**
   - Вставьте скриншот выполнения запроса

5.3 Выведите пользователей старше 50 лет:
   ```sql
   SELECT * FROM users WHERE age > 50;
   ```

---

## 6. Итоговое задание

1. Напишите `docker-compose.yml` для PostgreSQL.
2. Заполните базу тестовыми данными.
3. Подключитесь через DataGrip.
4. Выполните тестовые SQL-запросы.
5. Перезапустите контейнер и проверьте сохранность данных.
6. Создайте отчет с командами, скриншотами и комментариями.

## Инструкция по выполнению

1. Склонируйте этот репозиторий к себе на компьютер.
2. Отчет с выполненными заданиями в файле `./src/result.md`
3. Файл `docker-compose.yml` в папке `./src`
4. Изображение добавляете в папку `.src/img` и вставляете в отчет ссылку на изображение, например `![Скриншот](./img/screenshot.png)`
5. Сохраните kизменения и сделайте Push в ветку main GitHub своего репозитория
6. Ссылку на свою работу прикрепляете в качестве сдачи работы в Google Classroom


## Полезные ссылки

- [Docker](https://www.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [PostgreSQL](https://www.postgresql.org/)
- [DataGrip](https://www.jetbrains.com/datagrip/)
