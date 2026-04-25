# PCC Mock Server 配置说明文档

## 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [接口列表](#接口列表)
4. [任务创建接口](#任务创建接口)
5. [Mock数据关联机制](#mock数据关联机制)
6. [字段校验规则](#字段校验规则)
7. [使用示例](#使用示例)
8. [常见问题](#常见问题)

***

## 概述

PCC Mock Server 是济南城市轨道交通PCC接口通讯规范的模拟实现，用于辅助PIDS系统的接口测试。

### 核心特性

- **序号统一管理**：全局序号单调递增，保证ID唯一性
- **业务关联**：紧急文本、播放计划、版式通过业务序号关联
- **字段校验**：回传接口进行严格的必填字段校验
- **Web管理界面**：可视化配置和监控

***

## 快速开始

### 1. 安装依赖

```bash
pip install flask
```

### 2. 启动服务

```bash
cd "E:\pids\JY\济阳PCC-mock程序\v2_mock_server"
python pcc_mock_server.py
```

### 3. 访问Web界面

```
http://localhost:5000/
```

### 4. 配置PIDS

将PIDS的PCC接口地址配置为：

```
http://<mock服务器IP>:5000
```

***

## 接口列表

### 获取类接口（PIDS→PCC）

| 接口路径                                        | 方法  | 说明     | PIDS调用频率 |
| ------------------------------------------- | --- | ------ | -------- |
| `/mpis-intercut/api/task/cmd/metro`         | GET | 任务命令获取 | 1-5分钟/次  |
| `/mpis-intercut/api/play/schedules/taskId`  | GET | 播放计划获取 | 按需       |
| `/mpis-intercut/api/play/schedules/layout`  | GET | 版式获取   | 按需       |
| `/mpis-intercut/api/operate/emer/taskId`    | GET | 紧急信息获取 | 按需       |
| `/mpis-intercut/api/ctrl/devicectrl/taskId` | GET | 设备控制获取 | 按需       |

### 回传类接口（PIDS←PCC）

| 接口路径                                     | 方法   | 说明      | 触发条件    |
| ---------------------------------------- | ---- | ------- | ------- |
| `/mpis-intercut/api/ats/atsInfo/metro`   | POST | ATS信息接入 | ATS数据采集 |
| `/mpis-intercut/api/devicemonitor/metro` | POST | 设备状态监测  | 定时采集    |
| `/mpis-intercut/api/monitor/task/metro`  | POST | 设备任务反馈  | 任务执行完成  |

***

## 任务创建接口

### 1. 创建播放计划任务

**接口**: `GET /add_schedule_task`

**参数**:

| 参数           | 必填 | 说明            | 示例    |
| ------------ | -- | ------------- | ----- |
| metro        | 是  | 线路编号          | 20    |
| schedule\_id | 否  | 播放计划ID，默认自动生成 | 6001  |
| name         | 否  | 播放计划名称        | 站厅播出组 |

**示例**:

```bash
# 创建播放计划
curl "http://localhost:5000/add_schedule_task?metro=20&name=站厅播出组1"

# 指定ID创建
curl "http://localhost:5000/add_schedule_task?metro=20&schedule_id=6001&name=上午播表"
```

**返回值**:

```json
{
    "code": 0,
    "msg": "success",
    "taskId": "1001",
    "msgId": 1001,
    "taskUrl": "http://*.*.*.*:5000/mpis-intercut/api/play/schedules/taskId?taskId=1001"
}
```

### 2. 创建紧急信息任务

**接口**: `GET /add_emergency_task`

**参数**:

| 参数           | 必填 | 说明                    | 示例          |
| ------------ | -- | --------------------- | ----------- |
| metro        | 是  | 线路编号                  | 20          |
| level        | 否  | 级别(6-10全屏/1-5滚动)，默认10 | 10          |
| content      | 否  | 内容，默认"测试紧急信息内容"       | 紧急通知        |
| device\_list | 否  | 设备列表，逗号分隔             | S0001,S0002 |

**示例**:

```bash
# 创建全屏紧急信息
curl "http://localhost:5000/add_emergency_task?metro=20&level=10&content=全屏紧急测试"

# 创建滚动文本
curl "http://localhost:5000/add_emergency_task?metro=20&level=5&content=滚动文本测试"
```

### 3. 创建撤销任务

**接口**: `GET /add_cancel_task`

**参数**:

| 参数           | 必填 | 说明       | 示例          |
| ------------ | -- | -------- | ----------- |
| metro        | 是  | 线路编号     | 20          |
| msg\_id      | 是  | 要撤销的消息ID | 10001       |
| device\_list | 否  | 设备列表     | S0001,S0002 |

**示例**:

```bash
curl "http://localhost:5000/add_cancel_task?metro=20&msg_id=10001"
```

### 4. 创建设备控制任务

**接口**: `GET /add_device_control_task`

**参数**:

| 参数           | 必填                 | 说明           | 示例          |
| ------------ | ------------------ | ------------ | ----------- |
| metro        | 是                  | 线路编号         | 20          |
| cmd\_type    | 是                  | 命令类型         | 03          |
| left\_sound  | cmd\_type=04时必填    | 左声道音量(0-100) | 50          |
| right\_sound | cmd\_type=04时必填    | 右声道音量(0-100) | 50          |
| port         | cmd\_type=07/08时必填 | 屏幕端口         | 01          |
| device\_list | 否                  | 设备列表         | S0001,S0002 |

**命令类型说明**:

| cmdType | 说明   | 额外参数                  |
| ------- | ---- | --------------------- |
| 03      | 设备重启 | 无                     |
| 04      | 声音调整 | leftSound, rightSound |
| 05      | 关闭声音 | 无                     |
| 06      | 打开声音 | 无                     |
| 07      | 打开屏幕 | port                  |
| 08      | 关闭屏幕 | port                  |

**示例**:

```bash
# 设备重启
curl "http://localhost:5000/add_device_control_task?metro=20&cmd_type=03"

# 音量调整
curl "http://localhost:5000/add_device_control_task?metro=20&cmd_type=04&left_sound=70&right_sound=80"

# 打开屏幕
curl "http://localhost:5000/add_device_control_task?metro=20&cmd_type=07&port=01"
```

### 5. 任务管理

**删除任务**: `GET /delete_task?taskId=xxx&type=xxx`

- type可选: schedule, emergency, control

**清空所有任务**: `GET /clear_all_tasks`

**重置序号**: `GET /reset_sequence`

***

## Mock数据关联机制

### 序号管理策略

Mock Server使用全局序号管理器，保证所有ID单调递增：

```
任务ID: 1001, 1002, 1003, ...
消息ID: 10001, 10002, 10003, ...
```

### 业务关联关系

```
┌─────────────────────────────────────────────────────────────┐
│                     任务命令列表                              │
│  GET /mpis-intercut/api/task/cmd/metro?metro=20           │
└─────────────────────────────┬───────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ 播放计划任务  │    │ 紧急信息任务  │    │ 设备控制任务  │
│ taskType=10  │    │ taskType=1   │    │ taskType=51  │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        │                     │                     │
        ▼                     │                     │
┌───────────────┐             │                     │
│ 播放计划详情  │◄────────────┘                     │
│ /play/schedule│  (通过taskId关联)                  │
└───────┬───────┘                                    │
        │                                             │
        ▼                                             │
┌───────────────┐                                     │
│ 版式列表      │                                     │
│ layouts[]    │                                     │
└─────────────┘                                     │
```

### 示例场景

**场景1: 播放计划+版式**

```bash
# 1. 创建播放计划任务（自动关联版式）
curl "http://localhost:5000/add_schedule_task?metro=20&schedule_id=6001&name=站厅播出组"

# 2. PIDS获取任务列表
GET /mpis-intercut/api/task/cmd/metro?metro=20
# 返回: [{"taskType":10,"taskId":"6001",...}]

# 3. PIDS获取播放计划详情
GET /mpis-intercut/api/play/schedules/taskId?taskId=6001
# 返回: 包含layouts数组，每个layout有id

# 4. PIDS获取版式详情
GET /mpis-intercut/api/play/schedules/layout?layout=1001
# 返回: 版式完整信息
```

**场景2: 紧急信息发布+撤销**

```bash
# 1. 创建紧急发布任务
curl "http://localhost:5000/add_emergency_task?metro=20&level=10&content=紧急测试"

# 响应返回: {"taskId":"1002","msgId":"10001"}

# 2. 创建撤销任务（使用同一msgId）
curl "http://localhost:5000/add_cancel_task?metro=20&msg_id=10001"

# 3. PIDS获取任务列表
GET /mpis-intercut/api/task/cmd/metro?metro=20
# 返回: 两个任务，一个是发布，一个是撤销
```

***

## 字段校验规则

### ATS信息接入

**必填字段校验**:

```json
{
    "lineId": "20",           // 必填，线路ID
    "stationId": "0623",       // 必填，车站ID
    "atsInfo": [               // 必填，列车信息数组
        {
            "stationId": "0623",       // 必填，站台ID
            "direction": 1,           // 必填，方向(1=上行/2=下行)
            "platformId": "2",         // 必填，站台编号
            "trainCode": "T001",       // 必填，列车编号
            "arrivalTime": "...",     // 必填，到站时间
            "departureTime": "...",    // 必填，离站时间
            "status": 0,              // 必填，状态(0-3)
            "holdFlag": "false",       // 必填，扣车标识
            "skipFlag": "false",      // 必填，跳站标识
            "outOfService": "0",       // 必填，不载客标识
            "lastTrain": "0"           // 必填，首末班标识
        }
    ]
}
```

**status字段取值**:

- 0: 未知
- 1: 即将进站
- 2: 到站
- 3: 离站

**校验失败示例**:

```json
{
    "error": "atsInfo[0]缺少必填字段: trainCode; atsInfo[1]status值必须在0-3范围内，当前值: 5"
}
```

### 设备状态监测

**必填字段校验**:

```json
{
    "updatedTime": "2026-04-17 10:00:00",   // 必填，更新时间
    "lineCode": "20",                        // 必填，线路编号
    "deviceList": [                          // 必填，设备列表
        {
            "code": "S000000010301",          // 必填，设备编号
            "status": [                       // 必填，状态列表
                {
                    "fieldType": 6,           // 必填，字段类型
                    "field": "CPU使用率",      // 可选
                    "value": "45"              // 可选
                }
            ],
            "alarm": [                        // 可选，告警列表
                {
                    "fieldId": 1,             // 必填，告警编码
                    "levels": "2",            // 必填，告警等级
                    "reason": "设备离线"       // 必填，告警原因
                }
            ]
        }
    ]
}
```

**fieldType字段类型**:

| fieldType | 字段名称    | 单位      |
| --------- | ------- | ------- |
| 1         | 通信      | 1正常/0故障 |
| 2         | 开关      | 1开/0关   |
| 3         | 操作系统版本  | -       |
| 4         | CPU基本信息 | -       |
| 5         | CPU温度   | -       |
| 6         | CPU使用率  | %       |
| 7         | 内存总容量   | M       |
| 8         | 内存占用率   | %       |
| 9         | 磁盘总容量   | G       |
| 10        | 磁盘剩余容量  | G       |
| 11-13     | C/D/E盘  | -       |
| 14        | 软件版本    | -       |
| 15        | 当前播表    | -       |
| 16        | 当前版式    | -       |
| 17        | 紧急信息    | -       |
| 18        | 屏幕状态    | -       |

**fieldId告警编码**:

| fieldId | 告警名称    | levels |
| ------- | ------- | ------ |
| 1       | 通信      | 2      |
| 2       | 开关      | 3      |
| 3       | CPU温度   | 4      |
| 4       | CPU占用率  | 3      |
| 5       | 磁盘余量    | 3      |
| 6       | 播放异常    | 2      |
| 7       | 播出程序未开启 | 2      |
| 8       | 屏幕异常    | 3      |

### 设备任务反馈

**必填字段校验**:

```json
{
    "updatedTime": "2026-04-17 10:00:00",   // 必填，更新时间
    "lineCode": "20",                        // 必填，线路编号
    "deviceList": [                          // 必填，设备列表
        {
            "S000000010301": [               // key为设备ID
                {
                    "taskID": "445367548765", // 必填，任务ID
                    "retType": "02",          // 必填，回传类型(01进度/02结果)
                    "result": "1"              // 必填，结果(1成功/2失败)
                }
            ]
        }
    ]
}
```

**retType取值**:

- 01: 执行进度
- 02: 执行结果

**result取值**:

- 1: 成功
- 2: 失败（需配合reason字段说明原因）

***

## 使用示例

### 示例1: 完整播放计划测试流程

```bash
# 1. 启动服务
python pcc_mock_server.py

# 2. 创建播放计划任务
curl "http://localhost:5000/add_schedule_task?metro=20&schedule_id=6001&name=站厅播出组"

# 3. 查看Web界面
# http://localhost:5000/

# 4. PIDS端模拟调用
# GET /mpis-intercut/api/task/cmd/metro?metro=20
# 返回: [{"taskType":10,"taskId":"6001",...}]

# GET /mpis-intercut/api/play/schedules/taskId?taskId=6001
# 返回: 播放计划详情，包含layouts数组

# GET /mpis-intercut/api/play/schedules/layout?layout=1001
# 返回: 版式详情
```

### 示例2: 紧急信息测试

```bash
# 1. 创建全屏紧急信息(level=10)
curl "http://localhost:5000/add_emergency_task?metro=20&level=10&content=全屏紧急测试"

# 2. 创建滚动文本(level=5)
curl "http://localhost:5000/add_emergency_task?metro=20&level=5&content=滚动文本测试"

# 3. 创建撤销（使用第一个的msgId）
# 假设第一个返回 msgId=10001
curl "http://localhost:5000/add_cancel_task?metro=20&msg_id=10001"

# 4. PIDS获取并处理
# GET /mpis-intercut/api/task/cmd/metro?metro=20
# 返回3个任务：发布、滚动、撤销
```

### 示例3: 设备控制测试

```bash
# 1. 创建音量调整任务
curl "http://localhost:5000/add_device_control_task?metro=20&cmd_type=04&left_sound=70&right_sound=80"

# 2. PIDS获取任务
# GET /mpis-intercut/api/task/cmd/metro?metro=20
# 返回包含taskType=51的任务

# GET /mpis-intercut/api/ctrl/devicectrl/taskId?taskId=xxx
# 返回: {"ctrlCmd":[{"cmdType":"04","leftSound":70,"rightSound":80,...}]}

# 3. PIDS执行后回传结果
# POST /mpis-intercut/api/monitor/task/metro?metro=20
# Body: {"updatedTime":"...","lineCode":"20","deviceList":[{"S000000010301":[{"taskID":"xxx","retType":"02","result":"1"}]}]}
```

### 示例4: PIDS回传数据校验测试

```bash
# 1. 测试ATS信息接入（正确格式）
curl -X POST "http://localhost:5000/mpis-intercut/api/ats/atsInfo/metro?metro=20" \
  -H "Content-Type: application/json" \
  -d '{
    "lineId": "20",
    "stationId": "0623",
    "atsInfo": [{
      "stationId": "0623",
      "direction": 1,
      "platformId": "2",
      "trainCode": "T001",
      "arrivalTime": "2026-04-17 10:00:00",
      "departureTime": "2026-04-17 10:01:00",
      "status": 1,
      "holdFlag": "false",
      "skipFlag": "false",
      "outOfService": "0",
      "lastTrain": "0"
    }]
  }'
# 返回: {"code": 0, "msg": "success"}

# 2. 测试缺失字段
curl -X POST "http://localhost:5000/mpis-intercut/api/ats/atsInfo/metro?metro=20" \
  -H "Content-Type: application/json" \
  -d '{"lineId": "20"}'
# 返回: {"error": "缺少必填字段: stationId; 缺少必填字段: atsInfo"}
```

***

## 常见问题

### Q1: 如何保证任务ID不重复？

A: Mock Server使用全局序号管理器，每次创建任务时自动递增。即使服务重启，序号也会继续递增。如需重置，使用`/reset_sequence`接口。

### Q2: 如何模拟PIDS回传失败？

A: Mock Server会验证回传数据的必填字段，如果字段缺失会返回400错误并列出所有错误。

### Q3: 如何测试特定的边界值？

A: 可以直接在URL参数中指定值，例如：

```bash
# 测试content长度边界(1024字符)
curl "http://localhost:5000/add_emergency_task?metro=20&content=<1024个字符>"
```

### Q4: 如何查看接收到的回传数据？

A: Web界面的"最近接收"区域会显示最近5条记录。也可以通过查看服务日志获取完整信息。

### Q5: 多个PIDS客户端连接会有影响吗？

A: Mock Server是无状态的，支持多个客户端同时连接。每个客户端独立获取任务列表，独立回传数据。

***

## 附录

### 接口响应码

| 响应码 | 说明                 |
| --- | ------------------ |
| 200 | 成功                 |
| 400 | 请求参数错误（字段缺失、格式错误等） |
| 404 | 资源不存在              |
| 500 | 服务器内部错误            |

### 日志示例

```
[10:30:15] ✅ 创建播放计划任务: taskId=6001, name=站厅播出组, metro=20
[10:30:45] 📋 任务列表获取: metro=20, 任务数=3
[10:31:00] 📋 播放计划获取: taskId=6001
[10:31:15] 🎨 版式获取: layout=1001
[10:32:00] ✅ ATS信息接收成功: metro=20, 车站=0623, 列车数=2
[10:32:30] ✅ 任务反馈接收成功: metro=20, 设备数=5
[10:33:00] ❌ 设备状态校验失败: 缺少必填字段: updatedTime
```

