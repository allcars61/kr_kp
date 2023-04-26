import random
import psycopg2
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType

TOKEN = "your_vk_token_here"
POSTGRESQL_URI = "postgresql://username:password@localhost:5432/psqlname"

# настройки VK API
vk_session = vk_api.VkApi(token=TOKEN)
longpoll = VkLongPoll(vk_session)

try:
    conn = psycopg2.connect(POSTGRESQL_URI)
    cursor = conn.cursor()
except psycopg2.Error as e:
    print("Unable to connect to the database.")
    print(e)


# функция для работы с базой данных


def execute_query(query, values=()):
    cursor.execute(query, values)
    conn.commit()
    return cursor.fetchall()


# функция для отправки сообщений пользователю


def send_message(vk_session, user_id, message):
    vk_session.method(
        "messages.send",
        {
            "user_id": user_id,
            "message": message,
            "random_id": random.randint(0, 2**20),
        },
    )


def register_user(vk_session, user_id):
    execute_query("INSERT INTO users (vk_id) VALUES (%s)", (user_id,))
    execute_query("INSERT INTO preferences (user_id) VALUES (%s)", (user_id,))
    execute_query(
        "UPDATE users SET registration_step=%s WHERE vk_id=%s", ("sex", user_id)
    )
    send_message(
        vk_session,
        user_id,
        "Здравствуйте! Давайте зарегистрируем вас в нашем сервисе знакомств. Введите ваш пол (мужской или женский).",
    )


# обработка сообщений

for event in longpoll.listen():
    try:
        if event.type == VkEventType.MESSAGE_NEW and event.to_me:
            text = event.text
            user_id = event.user_id
            message = event.message

            if text == "/register":
                register_user(vk_session, user_id)

            elif (
                message.get("text")
                and execute_query(
                    "SELECT registration_step FROM users WHERE vk_id=%s", (user_id,)
                )[0][0]
                == "sex"
            ):
                sex = text.lower()
                execute_query(
                    "UPDATE preferences SET sex=%s WHERE user_id=%s", (sex, user_id)
                )
                execute_query(
                    "UPDATE users SET registration_step=%s WHERE vk_id=%s",
                    ("age", user_id),
                )
                send_message(
                    vk_session,
                    user_id,
                    'Введите возрастной диапазон, на который вы хотели бы ориентироваться, в формате "от ... до ...".',
                )

            elif (
                message.get("text")
                and execute_query(
                    "SELECT registration_step FROM users WHERE vk_id=%s", (user_id,)
                )[0][0]
                == "age"
            ):
                if "от" in text.lower() and "до" in text.lower():
                    age_from, age_to = text.lower().split("от")[1].split("до")
                    if age_from.isdigit() and age_to.isdigit():
                        execute_query(
                            "UPDATE preferences SET age_from=%s, age_to=%s WHERE user_id=%s",
                            (int(age_from), int(age_to), user_id),
                        )
                        execute_query(
                            "UPDATE users SET registration_step=%s WHERE vk_id=%s",
                            ("interests", user_id),
                        )
                        send_message(
                            vk_session, user_id, "Введите ваши интересы через запятую."
                        )
                    else:
                        send_message(
                            vk_session,
                            user_id,
                            'Некорректный формат ввода. Введите возрастной диапазон в формате "от ... до ...".',
                        )

                else:
                    send_message(
                        vk_session,
                        user_id,
                        'Некорректный формат ввода. Введите возрастной диапазон в формате "от ... до ...".',
                    )

            elif (
                message.get("text")
                and execute_query(
                    "SELECT registration_step FROM users WHERE vk_id=%s", (user_id,)
                )[0][0]
                == "interests"
            ):
                interests = set(text.lower().split(", "))
                execute_query(
                    "UPDATE preferences SET interests=%s WHERE user_id=%s",
                    (str(interests), user_id),
                )
                execute_query(
                    "UPDATE users SET registration_step=%s WHERE vk_id=%s",
                    ("finished", user_id),
                )
                send_message(vk_session, user_id, "Профиль успешно обновлен!")

            elif (
                message.get("text")
                and execute_query(
                    "SELECT registration_step FROM users WHERE vk_id=%s", (user_id,)
                )[0][0]
                == "finished"
            ):
                preferences = execute_query(
                    "SELECT sex, age_from, age_to, interests FROM preferences WHERE user_id=%s",
                    (user_id,),
                )[0]
                sex, age_from, age_to, interests = preferences
                matches = execute_query(
                    "SELECT vk_id FROM preferences WHERE sex=%s AND age_from<=%s AND age_to>=%s AND interests && %s AND vk_id!=%s",
                    (sex, age_from, age_to, list(interests), user_id),
                )
                if len(matches) > 0:
                    match_ids = [match[0] for match in matches]
                    match_names = vk_session.method(
                        "users.get",
                        {
                            "user_ids": ",".join(map(str, match_ids)),
                            "fields": "first_name, last_name",
                        },
                    )
                    message = "Вот ваши потенциальные матчи:\n\n"
                    for match in match_names:
                        name = f"{match['first_name']} {match['last_name']}"
                        message += f"{name}\nhttps://vk.com/id{match['id']}\n\n"
                else:
                    message = "К сожалению, нет пользователей, подходящих вашим предпочтениям."
                send_message(vk_session, user_id, message)

    except Exception as e:
        print(e)
    finally:
        cursor.close()
        conn.close()

