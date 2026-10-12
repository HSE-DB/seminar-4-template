from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT = ROOT / "src" / "assignment"
POSTGRES_IMAGES = {"postgres:18", "docker.io/library/postgres:18"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class DockerAssignmentTests(unittest.TestCase):
    started = False
    temporary = None

    @classmethod
    def command(cls, args, *, check=True, timeout=180):
        try:
            result = subprocess.run(
                args,
                cwd=cls.work,
                env=cls.environment,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise RuntimeError("Не найдена команда docker. Установите Docker с Compose.") from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Команда не завершилась за {timeout} секунд: {' '.join(args)}") from error
        if check and result.returncode:
            details = (result.stdout + "\n" + result.stderr).strip()[-4000:]
            raise AssertionError(f"Ошибка команды {' '.join(args)}:\n{details}")
        return result

    @classmethod
    def compose(cls, *args, **kwargs):
        return cls.command(cls.base + list(args), **kwargs)

    @classmethod
    def sql(cls, query):
        return cls.compose(
            "exec", "-T", "-e", "PGPASSWORD=student", "db", "psql",
            "-h", "127.0.0.1", "-U", "student", "-d", "practice",
            "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", query,
        ).stdout.strip()

    @classmethod
    def db_details(cls):
        container_id = cls.compose("ps", "-q", "db").stdout.strip()
        require(container_id, "Контейнер db должен работать.")
        return json.loads(cls.command(["docker", "inspect", container_id]).stdout)[0]

    @classmethod
    def validate_config(cls, model):
        services = model.get("services", {})
        require(set(services) == {"db", "client"}, "Нужны ровно два сервиса: db и client.")
        for name, service in services.items():
            require(service.get("image") in POSTGRES_IMAGES, f"{name}: используйте postgres:18.")
            require(not service.get("build"), f"{name}: используйте готовый образ без build.")
            require(not service.get("container_name"), f"{name}: не задавайте container_name.")
            for field in ("privileged", "devices", "cap_add", "network_mode", "pid", "ipc", "volumes_from", "extends", "extra_hosts"):
                require(not service.get(field), f"{name}: поле {field} в этом задании не требуется.")
            require(set(service.get("networks", {})) == {"default"}, f"{name}: используйте обычную сеть проекта.")

        networks = model.get("networks", {})
        require(set(networks) == {"default"}, "Используйте только default-сеть проекта.")
        network = networks["default"]
        require(not network.get("external"), "Сеть не должна быть external.")
        require(network.get("name") == cls.project + "_default", "Не задавайте фиксированное имя сети.")
        require(network.get("driver", "bridge") == "bridge" and not network.get("driver_opts"), "Используйте обычную bridge-сеть без driver_opts.")

        volumes = model.get("volumes", {})
        require(set(volumes) == {"pgdata"}, "Объявите один именованный volume pgdata.")
        volume = volumes["pgdata"]
        require(not volume.get("external"), "pgdata не должен быть external.")
        require(volume.get("name") == cls.project + "_pgdata", "Не задавайте фиксированное имя volume.")
        require(volume.get("driver", "local") == "local" and not volume.get("driver_opts"), "Используйте обычный локальный volume.")

        db = services["db"]
        require(not db.get("command") and not db.get("entrypoint"), "Не заменяйте команду и entrypoint сервера PostgreSQL.")
        expected = {"POSTGRES_USER": "student", "POSTGRES_PASSWORD": "student", "POSTGRES_DB": "practice"}
        for key, value in expected.items():
            require(db.get("environment", {}).get(key) == value, f"Передайте db переменную {key} из учебных настроек.")

        ports = db.get("ports", [])
        require(len(ports) == 1, "Опубликуйте только порт PostgreSQL.")
        port = ports[0]
        require(port.get("target") == 5432 and port.get("host_ip") == "127.0.0.1", "Публикация должна вести с 127.0.0.1 к 5432 контейнера.")
        require(str(port.get("published")) == "0", "Внешний порт должен использовать переменную PG_PORT: тест подставляет 0.")
        require(port.get("protocol", "tcp") == "tcp", "Для PostgreSQL требуется TCP.")

        mounts = db.get("volumes", [])
        require(len(mounts) == 2, "У db должны быть только mounts pgdata и init.sql.")
        data_mount = next((m for m in mounts if m.get("type") == "volume"), {})
        require(data_mount.get("source") == "pgdata" and data_mount.get("target") == "/var/lib/postgresql", "Подключите pgdata к /var/lib/postgresql для PostgreSQL 18.")
        require(not data_mount.get("read_only"), "Volume данных должен разрешать запись.")
        init_mount = next((m for m in mounts if m.get("type") == "bind"), {})
        require(init_mount.get("target") == "/docker-entrypoint-initdb.d/10-init.sql", "Подключите init.sql к /docker-entrypoint-initdb.d/10-init.sql.")
        require(Path(init_mount.get("source", "")).resolve() == (cls.work / "init.sql").resolve(), "Исходный SQL должен находиться в ./init.sql задания.")
        require(init_mount.get("read_only") is True, "Подключите init.sql только для чтения.")

        health = db.get("healthcheck", {})
        test = health.get("test", [])
        require(not health.get("disable") and isinstance(test, list), "Добавьте healthcheck для db.")
        health_command = " ".join(str(part) for part in test)
        require("pg_isready" in health_command and "127.0.0.1" in health_command, "Healthcheck должен использовать pg_isready по TCP 127.0.0.1.")

        client = services["client"]
        require(client.get("profiles") == ["tools"], "Добавьте client профиль tools.")
        require(not client.get("ports") and not client.get("volumes"), "Клиенту не нужны ports и mounts.")
        require(client.get("depends_on", {}).get("db", {}).get("condition") == "service_healthy", "Client должен ждать service_healthy у db.")
        expected_client = {"PGHOST": "db", "PGUSER": "student", "PGDATABASE": "practice", "PGPASSWORD": "student"}
        for key, value in expected_client.items():
            require(client.get("environment", {}).get(key) == value, f"Передайте клиенту {key} согласно заданию.")

    @classmethod
    def setUpClass(cls):
        for filename in ("compose.yaml", "init.sql", ".env.example"):
            source = ASSIGNMENT / filename
            require(source.is_file() and source.read_text().strip(), f"Заполните src/assignment/{filename}.")

        cls.project = "hse4-check-" + uuid.uuid4().hex[:12]
        cls.temporary = tempfile.TemporaryDirectory(prefix=cls.project + "-")
        cls.work = Path(cls.temporary.name)
        cls.addClassCleanup(cls.cleanup_project)
        for filename in ("compose.yaml", "init.sql", ".env.example"):
            shutil.copyfile(ASSIGNMENT / filename, cls.work / filename)

        cls.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("COMPOSE_")
            and key not in {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "PG_PORT"}
        }
        cls.environment.update({"PG_PORT": "0", "COMPOSE_ANSI": "never"})
        cls.base = [
            "docker", "compose", "--project-directory", str(cls.work),
            "--env-file", str(cls.work / ".env.example"),
            "-p", cls.project, "-f", str(cls.work / "compose.yaml"),
            "--profile", "tools",
        ]
        cls.environment["PG_PORT"] = "55434"
        initial_model = json.loads(cls.compose("config", "--format", "json").stdout)
        initial_ports = initial_model.get("services", {}).get("db", {}).get("ports", [])
        require(len(initial_ports) == 1 and str(initial_ports[0].get("published")) == "55434", "PG_PORT должен управлять внешним портом db.")
        cls.environment["PG_PORT"] = "0"
        model = json.loads(cls.compose("config", "--format", "json").stdout)
        cls.validate_config(model)
        cls.started = True
        cls.compose("up", "-d", "--wait", "--wait-timeout", "90", "db")

    @classmethod
    def cleanup_project(cls):
        if cls.started:
            result = cls.compose("down", "-v", "--remove-orphans", check=False)
            require(result.returncode == 0, "Не удалось удалить временный проект " + cls.project + ": " + result.stderr)
            cls.started = False
        if cls.temporary is not None:
            cls.temporary.cleanup()

    def test_01_server_ready_and_port(self):
        details = self.db_details()
        self.assertEqual(details["State"]["Health"]["Status"], "healthy")
        self.assertTrue(self.sql("SHOW server_version_num;").startswith("18"))
        published = details["NetworkSettings"]["Ports"].get("5432/tcp") or []
        self.assertTrue(any(p["HostIp"] == "127.0.0.1" and int(p["HostPort"]) > 0 for p in published))

    def test_02_schema_and_initial_rows(self):
        columns = self.sql(
            "SELECT column_name || ':' || is_nullable || ':' || data_type "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "AND table_name = 'users' ORDER BY ordinal_position;"
        ).splitlines()
        schema = {row.split(":", 2)[0]: row.split(":", 2)[1:] for row in columns}
        self.assertEqual(set(schema), {"id", "name", "age"})
        for column in schema:
            self.assertEqual(schema[column][0], "NO", f"{column} должен быть NOT NULL")
        for column in ("id", "age"):
            self.assertIn(schema[column][1], {"smallint", "integer", "bigint"})
        self.assertIn(schema["name"][1], {"text", "character varying", "character"})
        primary_key = self.sql(
            "SELECT string_agg(kcu.column_name, ',' ORDER BY kcu.ordinal_position) "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "USING (constraint_catalog, constraint_schema, constraint_name) "
            "WHERE tc.table_schema = 'public' AND tc.table_name = 'users' "
            "AND tc.constraint_type = 'PRIMARY KEY';"
        )
        self.assertEqual(primary_key, "id")
        self.assertEqual(self.sql("SELECT name || ':' || age FROM users ORDER BY name;"), "Alice:20\nBob:30\nCarol:40")

    def test_03_client_uses_sql_and_password(self):
        result = self.compose("run", "--rm", "--no-deps", "client")
        self.assertEqual(result.stdout.strip(), "3", "Client должен вывести только количество строк.")
        wrong = self.compose("run", "--rm", "--no-deps", "-e", "PGPASSWORD=wrong", "client", check=False)
        self.assertNotEqual(wrong.returncode, 0, "Клиент должен использовать переданный пароль, а не печатать константу.")
        self.assertIn("password authentication failed", wrong.stderr.lower())

    def test_04_data_survives_recreation(self):
        marker = "test_marker_" + uuid.uuid4().hex
        marker_id = self.sql(f"INSERT INTO users (name, age) VALUES ('{marker}', 99) RETURNING id;")
        before = self.db_details()
        before_mount = next(m for m in before["Mounts"] if m["Destination"] == "/var/lib/postgresql")
        self.assertEqual(before_mount["Name"], self.project + "_pgdata")
        self.compose("down")
        self.compose("up", "-d", "--wait", "--wait-timeout", "90", "db")
        after = self.db_details()
        after_mount = next(m for m in after["Mounts"] if m["Destination"] == "/var/lib/postgresql")
        self.assertNotEqual(before["Id"], after["Id"], "Проверка должна пересоздать контейнер.")
        self.assertEqual(before_mount["Name"], after_mount["Name"])
        self.assertEqual(self.sql(f"SELECT id FROM users WHERE name = '{marker}';"), marker_id)
        self.assertEqual(self.sql("SELECT count(*) FROM users;"), "4")
        self.assertEqual(self.compose("run", "--rm", "--no-deps", "client").stdout.strip(), "4")


if __name__ == "__main__":
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(DockerAssignmentTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    finally:
        DockerAssignmentTests.cleanup_project()
    sys.exit(0 if result.wasSuccessful() else 1)
