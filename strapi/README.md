# Strapi Admin Service

这个目录用于存放 Strapi 项目，负责用户、权限以及后续的后台管理功能。

## 初始化 Strapi

```bash
cd strapi
npx create-strapi-app@latest admin --quickstart --ts
```

完成后：

1. 访问 `http://localhost:1337/admin` 创建管理员账号。
2. 在 `Users & Permissions` 插件里，为 `Authenticated` 角色开启 `find`, `findOne`, `me` 接口权限。
3. 通过 Strapi 控制台创建前端用户，或者开放自注册。
4. 根据需要新增内容类型，用于记录批量转换任务、配额等信息。

## FastAPI 与 Strapi 的对接

FastAPI 服务通过校验 Strapi 下发的 JWT 来识别用户，配置项在 `backend/.env` 中：

```
STRAPI_BASE_URL=http://localhost:1337
STRAPI_DEV_TOKENS={"dev-token": {"id": 1, "username": "dev", "email": "dev@example.com"}}
```

- 开发阶段可使用 `dev-token` 直接调用接口；线上环境请移除该项，改为使用 Strapi 的登录接口 `/api/auth/local` 获取真实 token。
- FastAPI 调用 `GET /api/users/me` 验证 token，同步返回用户的 id / email 存入任务记录。

接下来可在 Strapi 中扩展更多后台功能（如任务列表、操作日志、配额管理等），并通过 REST/GraphQL 与当前的转换服务联动。
