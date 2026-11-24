# DSH Host API 接入

## 页面

- 插件中心：`/plugins`
- DSH 插件市场 / Host API：`/plugins/dsh`

## 连接

DSH Web 的 `/api` 不是匿名接口，需要浏览器会话 cookie。项目使用 DSH 启动 URL 中的
**launch token** 换取 cookie：

```text
dsh web: http://127.0.0.1:6602/?token=...
```

在页面填入：

- Base URL：与 DSH 实例一致，例如 `http://127.0.0.1:6602`
- Token：URL 中 `token=` 后面的值

token 只保存在本机 `data/dsh_host.json`，不会回传前端；页面上的 token 输入框只用于更新。

## 协议

连接后，后端向 DSH 发：

```http
POST /api/<namespace>/<method>
Content-Type: application/json

{
  "type": "client-request",
  "rpcId": "<uuid>",
  "method": "<namespace>/<method>",
  "payload": { "args": { "<参数名>": ... } }
}
```

认证流程：

```http
GET /?token=<launch-token>
```

DSH 返回 303 + HttpOnly cookie，后续 API 请求携带该 cookie。

## 已接方法

- `pluginManager/listBundles`
- `pluginManager/inspect`
- `pluginManager/installBundle`
- `pluginManager/setBundleEnabled`
- `pluginManager/removeBundle`
- `pluginMarket/listIndexes`
- `pluginMarket/setIndexes`
- `pluginMarket/search`

对应项目接口见 `webapp/API_CONTRACT.md`。

## 限制

- `pluginMarket` 是可选 bundle；当前 web profile 未启用时返回 404。
  可先用 Host API 安装 `@deepseek-ai/dsh-experimental-plugin-market-bundle`，
  或直接在 DSH 原生插件页操作。
- 安装/删除会修改 DSH profile；页面要求二次确认。
- token 等同本机 DSH 控制权限，不要写入仓库或发给他人。
