# ШІ: Claude sonnet 5.5 – Перевірка коду
class Member:

    def __init__(self, member_id, name, role):
        if not isinstance(member_id, int) or isinstance(member_id, bool) or member_id <= 0:
            raise ValueError("ID учасника має бути додатним цілим числом.")

        self._id = member_id
        self.name = name
        self.role = role

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Ім'я учасника має бути непорожнім рядком.")
        self._name = value.strip()

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Роль учасника має бути непорожнім рядком.")
        self._role = value.strip()

    def __str__(self):
        return f"{self.name} ({self.role})"