workspace {
    name "Task Planner"
    !identifiers hierarchical

    model {
        assignee = person "Исполнитель" "Выполняет задачи и меняет их статус" "assignee"
        admin = person "Администратор" "Управляет пользователями, системой, целями и задачами"

        // Система
        ss = softwareSystem "Task Planner" "Система для управления целями и задачами" {

            userDatabase = container "User Database" "Хранение данных о пользователях" "PostgreSQL Database" {
                tags "Database"
            }
            goalsDatabase = container "Goals & Tasks Database" "Хранение данных о целях и задачах" "MongoDB 5.0 Database" {
                tags "Database"
            }
            redisCache = container "Redis Cache" "Кэш для ускорения работы user-service" "Redis" {
                tags "Cache"
            }

            userService = container "User Service" "Управление пользователями (CRUD), аутентификация и кэширование" "Python (FastAPI)" {
                -> userDatabase "Читает и записывает данные пользователей (CRUD)" "SQLAlchemy"
                -> redisCache "Читает и записывает кэшированные данные пользователей" "Redis"
            }

            goalsService = container "Goals & Tasks Service" "Управление целями и задачами" "Python (FastAPI)" {
                -> goalsDatabase "Читает и записывает данные целей и задач (CRUD)" "pymongo"
                -> userService "Проверяет существование пользователя" "REST API"
            }
        }

        assignee -> ss "Для просмотра целей и задач и изменения их статуса"
        assignee -> ss.goalsService "Отправляет запросы на просмотр и изменение задач" "REST API" {
            tags "assignee_interaction"
        }

        admin -> ss "Использует для управления пользователями, аутентификацией, целями и задачами"
        admin -> ss.userService "Отправляет CRUD запросы для пользователей и запросы на аутентификацию" "REST API"
        admin -> ss.goalsService "Отправляет запросы на управление целями и задачами" "REST API"
    }

    views {
        systemContext ss {
            include *
            autolayout lr
            description "Системный контекст Task Planner, показывающий внешних пользователей и систему."
        }

        container ss {
            include *
            autolayout lr
            description "Контейнер Task Planner, показывающий основные сервисы, данные пользователей (PostgreSQL), данные целей и задач (MongoDB) и кэш Redis."
        }
        
        dynamic ss "User_Authentication" "Аутентификация пользователя (Администратор или Исполнитель)" {
            autoLayout lr
            admin -> ss.userService "Отправить POST-запрос на создание токена" "REST API"
            ss.userService -> ss.userDatabase "Проверить учетные данные пользователя в БД" "SQLAlchemy"
            ss.userDatabase -> ss.userService "Вернуть результат проверки" "SQLAlchemy"
            ss.userService -> admin "Сгенерировать JWT токен / Вернуть ошибку" "REST API"
        }

        dynamic ss "Create_Task_With_Assignee_Validation" "Создание задачи администратором (с проверкой assignee)" {
            autoLayout lr
            admin -> ss.goalsService "Отправить POST-запрос на создание задачи к цели с привязкой к исполнителю (assignee_id)" "REST API"
            ss.goalsService -> ss.userService "Проверить существование исполнителя по assignee_id" "REST API"
            ss.userService -> ss.userDatabase "Проверить существование пользователя (исполнителя) в БД" "SQLAlchemy"
            ss.userDatabase -> ss.userService "Вернуть результат проверки (найден/не найден)" "SQLAlchemy"
            ss.userService -> ss.goalsService "Вернуть результат проверки существования исполнителя" "REST API"
            ss.goalsService -> ss.goalsDatabase "Сохранить задачу в MongoDB" "pymongo"
            ss.goalsDatabase -> ss.goalsService "Вернуть созданную задачу" "pymongo"
            ss.goalsService -> admin "Вернуть созданную задачу" "REST API"
        }

        dynamic ss "Assignee_Change_Task_Status" "Изменение статуса задачи исполнителем" {
            autoLayout lr
            assignee -> ss.goalsService "Отправить PUT-запрос на изменение статуса задачи" "REST API"
            ss.goalsService -> ss.goalsDatabase "Обновить статус задачи в MongoDB" "pymongo"
            ss.goalsDatabase -> ss.goalsService "Вернуть обновленную задачу" "pymongo"
            ss.goalsService -> assignee "Вернуть обновленную задачу" "REST API"
        }

        styles {
            element "Person" {
                shape person
                fontSize 22
            }
            element "Software System" {
                background #1168bd
                color #ffffff
                fontSize 22
            }
            element "Container" {
                background #438dd5
                color #ffffff
                fontSize 20
            }
            element "Database" {
                shape Cylinder
                background #FFBF00
                color #000000
            }
            element "Cache" {
                shape Cylinder
                background #FF6600
                color #ffffff
            }
            element "assignee" {
                icon "https://structurizr.com/img/user.png"
            }
        }
    }
}