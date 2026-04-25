# -*- coding: utf-8 -*-
"""
PCC Mock Server - 济南城市轨道交通PCC接口模拟服务器
=============================================
支持PIDS-PCC全部接口的Mock实现

接口列表：
  获取类接口（PIDS←PCC）：
    - GET  /mpis-intercut/api/task/cmd/metro              - 任务命令获取
    - GET  /mpis-intercut/api/play/schedules/taskId       - 播放计划获取
    - GET  /mpis-intercut/api/play/schedules/layout       - 版式获取
    - GET  /mpis-intercut/api/operate/emer/taskId         - 紧急信息获取
    - GET  /mpis-intercut/api/ctrl/devicectrl/taskId     - 设备控制指令获取

  回传类接口（PIDS→PCC）：
    - POST /mpis-intercut/api/ats/atsInfo/metro             - ATS信息接入
    - POST /mpis-intercut/api/devicemonitor/metro          - 设备状态监测接入
    - POST /mpis-intercut/api/monitor/task/metro           - 设备任务状态反馈

作者：Claude
版本：2.0
"""

from flask import Flask, request, jsonify
import datetime
import random
import time
import json
import hashlib

app = Flask(__name__)

# ========================
# 全局配置
# ========================
CONFIG = {
    'port': 5000,                    # 服务端口
    'default_metro': '20',            # 默认线路编号
    'max_content_length': 1024,       # 紧急文本最大长度
    'log_enabled': True,               # 是否打印日志
}

# ========================
# 序号管理器 - 保证全局序号单调递增
# ========================
class SequenceManager:
    """全局序号管理器，保证ID单调递增"""

    def __init__(self):
        self._task_counter = 1000      # 任务ID计数器
        self._msg_counter = 10000      # 消息ID计数器
        self._lock_counter = 100        # 锁序列计数器

    def next_task_id(self):
        """生成下一个任务ID"""
        self._task_counter += 1
        return str(self._task_counter)

    def next_msg_id(self):
        """生成下一个消息ID"""
        self._msg_counter += 1
        return str(self._msg_counter)

    def next_lock_id(self):
        """生成下一个锁序列ID"""
        self._lock_counter += 1
        return str(self._lock_counter)

    def reset(self):
        """重置所有计数器"""
        self._task_counter = 1000
        self._msg_counter = 10000
        self._lock_counter = 100

# 全局序号管理器实例
seq_manager = SequenceManager()

# ========================
# Mock数据存储
# ========================
class MockDataStore:
    """Mock数据存储，支持业务关联"""

    def __init__(self):
        # 任务存储 {taskId: task_data}
        self.tasks = {}

        # 播放计划存储 {taskId: schedule_data}
        self.schedules = {}

        # 版式存储 {layoutId: layout_data}
        self.layouts = {}

        # 紧急信息存储 {taskId: emer_data}
        self.emergencies = {}

        # 设备控制存储 {taskId: ctrl_data}
        self.controls = {}

        # 接收到的回传数据日志
        self.received_ats = []
        self.received_monitor = []
        self.received_device_status = []

    def clear_all(self):
        """清空所有数据"""
        self.tasks.clear()
        self.schedules.clear()
        self.layouts.clear()
        self.emergencies.clear()
        self.controls.clear()
        self.received_ats.clear()
        self.received_monitor.clear()
        self.received_device_status.clear()

    def add_schedule_with_layouts(self, task_id, metro_id, schedule_data, device_list=None):
        """添加播放计划及其关联的版式"""
        # 统一转换为int类型，避免字符串/整数key不匹配问题
        task_id = int(task_id)
        self.schedules[task_id] = schedule_data.copy()
        # 默认设备列表
        default_devices = ['S00000001040', 'S00000001042']
        # 使用传入的设备列表，否则用默认设备
        final_devices = device_list if (device_list is not None and len(device_list) > 0) else default_devices
        # 关联任务（无论是否已存在，都设置设备）
        if task_id not in self.tasks:
            self.tasks[task_id] = {
                'taskId': task_id,
                'taskType': '10',  # 播放计划任务
                'metroId': metro_id,
                'updatedTime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'deviceList': final_devices
            }
        else:
            # 任务已存在，更新设备列表
            self.tasks[task_id]['deviceList'] = final_devices

    def add_emergency(self, task_id, metro_id, emer_data, device_list=None):
        """添加紧急信息"""
        # 统一转换为int类型，避免字符串/整数key不匹配问题
        task_id = int(task_id)
        self.emergencies[task_id] = emer_data.copy()
        # 默认设备列表
        default_devices = ['S00000001040', 'S00000001042']
        # 使用传入的设备列表，否则用默认设备
        final_devices = device_list if (device_list is not None and len(device_list) > 0) else default_devices
        # 关联任务（无论是否已存在，都设置设备）
        if task_id not in self.tasks:
            self.tasks[task_id] = {
                'taskId': task_id,
                'taskType': '1',  # 紧急信息发布
                'metroId': metro_id,
                'updatedTime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'deviceList': final_devices
            }
        else:
            # 任务已存在，更新设备列表
            self.tasks[task_id]['deviceList'] = final_devices

    def add_cancel(self, task_id, metro_id, msg_id):
        """添加撤销任务"""
        # 统一转换为int类型，避免字符串/整数key不匹配问题
        task_id = int(task_id)
        self.tasks[task_id] = {
            'taskId': task_id,
            'taskType': '3',  # 撤销
            'metroId': metro_id,
            'msgId': msg_id,
            'updatedTime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'deviceList': []
        }

    def add_control(self, task_id, metro_id, ctrl_data):
        """添加设备控制任务"""
        self.controls[task_id] = ctrl_data.copy()
        if task_id not in self.tasks:
            self.tasks[task_id] = {
                'taskId': task_id,
                'taskType': '51',  # 设备控制
                'metroId': metro_id,
                'updatedTime': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'deviceList': ctrl_data.get('deviceList', [])
            }

# 全局数据存储实例
data_store = MockDataStore()

# ========================
# 辅助函数
# ========================
def log(msg):
    """打印日志"""
    if CONFIG['log_enabled']:
        # 移除emoji避免Windows编码问题
        import re
        msg_clean = re.sub(r'[\u2600-\u26FF\u2700-\u27BF\U00010000-\U0010ffff]', '', msg)
        try:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg_clean}")
        except UnicodeEncodeError:
            # 强制用utf-8编码
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg_clean.encode('utf-8', errors='ignore').decode('utf-8')}")

def generate_layout(params=None):
    """生成版式数据"""
    if params is None:
        params = {}

    layout_id = params.get('id', seq_manager.next_task_id())
    layout_type = params.get('type', 'single')  # single 或 double

    # 生成不同类型版式的partitions
    if layout_type == 'single':
        partitions = generate_single_trans_partitions()
    else:
        partitions = generate_double_trans_partitions()

    return {
        "id": int(layout_id),
        "name": params.get('name', f'版式{layout_id}'),
        "updatedTime": params.get('updatedTime', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "resolution": params.get('resolution', '1920,1080'),
        # 底图，确保能访问，以及md5正确
        "backImage": params.get('backImage', 'http://172.25.10.146:9001/pids-fastdfs/fastdfs/preview-fastDFS?groupName=group1&filePath=M00/00/15/rBkKkmnYcC2EZHIZAAAAAD0IOYU436.png'),
        "md5": params.get('md5', 'cbc7216def3d235ea7e382dabda39609'),
        "backColor": params.get('backColor', ''),
        "showType": params.get('showType', 0),
        "partitions": params.get('partitions', partitions),
        "emer": {
            "fullScreen": {
                "backImage": None,
                "md5": None,
                "backColor": "#F44336",
                "font": {
                    "name": "黑体",
                    "size": 96,
                    "bold": None,
                    "italic": None,
                    "textColor": "#FFEB3B",
                    "align": 0,
                    "effect": 0
                }
            },
            "speed": 20,
            "showType": 3
        },
        "chEnSwitch": params.get('chEnSwitch', "5")
    }

def generate_schedule(params=None):
    """生成播放计划数据"""
    if params is None:
        params = {}

    schedule_id = params.get('id', seq_manager.next_task_id())

    # 生成关联的版式
    layouts = params.get('layouts', [
        {
            "id": 1000,
            "name": "默认版式",
            "updatedTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "startTime": "00:00:00",
            "endTime": "00:00:00",
            "weekFlag": ""
        },
        {
            "id": 1001,
            "name": "上午版式",
            "updatedTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "startTime": "07:00:00",
            "endTime": "12:00:00",
            "weekFlag": "1,2,3,4,5,6,7"
        }
    ])

    # 存储版式数据
    for layout in layouts:
        layout_id = layout['id']
        data_store.layouts[str(layout_id)] = generate_layout({'id': layout_id, 'name': layout['name']})

    return {
        "taskId": str(schedule_id),
        "id": int(schedule_id),
        "name": params.get('name', f'播放计划{schedule_id}'),
        "updatedTime": params.get('updatedTime', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "startTime": params.get('startTime', '2026-04-01 00:00:00'),
        "endTime": params.get('endTime', '2026-04-30 23:59:59'),
        "weekFlag": params.get('weekFlag', '1,2,3,4,5,6,7'),
        "resolution": params.get('resolution', '1920,1080'),
        "level": params.get('level', 3),
        "layouts": layouts
    }

def generate_emergency(level=10, content=None):
    """生成紧急信息数据"""
    if content is None:
        content = "测试紧急信息内容" if level >= 6 else "滚动文本测试内容"

    msg_id = seq_manager.next_msg_id()

    return {
        "msgId": msg_id,
        "levels": str(level),
        "content": content[:CONFIG['max_content_length']],
        "createTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "startTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if level <= 5 else "",
        "endTime": (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S") if level <= 5 else ""
    }

def generate_control(cmd_type, device_list=None, params=None):
    """生成设备控制数据"""
    if params is None:
        params = {}

    if device_list is None:
        device_list = ['S000000010301', 'S000000010302']

    return {
        "cmdType": str(cmd_type),
        "cmdValid": params.get('cmdValid', 1),
        "createTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "leftSound": params.get('leftSound', 50),
        "rightSound": params.get('rightSound', 50),
        "port": params.get('port', '01'),
        "planID": params.get('planID', ''),
        "deviceList": device_list
    }

def generate_single_trans_partitions():
    """生成单列车版式的partitions"""
    return [
        {
            "id": 901,
            "mediaType": 9,
            "rect": "878,8,678,184",
            "backImage": "",
            "md5": "",
            "backColor": None,
            "params": {
                "stationCh": {
                    "rect": "10,10,130,30",
                    "tipCh": None,
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    },
                    "content": {
                        "rect": "9,20,669,130",
                        "text": "市民中心",
                        "font": {
                            "name": "黑体",
                            "size": 72,
                            "bold": True,
                            "italic": True,
                            "textColor": "#000000",
                            "align": 2,
                            "effect": 0
                        }
                    }
                },
                "stationEn": {
                    "rect": "10,50,130,30",
                    "tip": None,
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    },
                    "content": {
                        "rect": "140,50,130,30",
                        "text": None,
                        "font": {
                            "name": "微软雅黑",
                            "size": 12,
                            "bold": False,
                            "italic": False,
                            "textColor": None,
                            "align": 1,
                            "effect": 0
                        }
                    }
                }
            },
            "zOrder": 3
        },
        {
            "id": 501,
            "mediaType": 5,
            "rect": "1572,14,330,80",
            "backImage": None,
            "md5": None,
            "backColor": None,
            "params": {
                "time": {
                    "format": "hh:mm:ss",
                    "font": {
                        "name": "黑体",
                        "size": 72,
                        "bold": False,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 2,
                        "effect": 0
                    }
                },
                "timeImage": None,
                "md5": None
            },
            "zOrder": 3
        },
        {
            "id": 401,
            "mediaType": 4,
            "rect": "1578,101,320,93",
            "backImage": None,
            "md5": None,
            "backColor": None,
            "params": {
                "date": {
                    "formatCh": "yyyy年mm月dd日",
                    "fontCh": {
                        "name": "黑体",
                        "size": 40,
                        "bold": False,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 2,
                        "effect": 0
                    },
                    "rectCh": "3,11,314,70",
                    "rectEn": "70,50,120,30",
                    "formatEn": "yyyy-mm-dd",
                    "fontEn": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                },
                "week": {
                    "formatCh": "EE",
                    "fontCh": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 1,
                        "effect": 0
                    },
                    "formatEn": None,
                    "fontEn": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    },
                    "rectCh": "130,10,80,30",
                    "rectEn": "130,50,80,30"
                }
            },
            "zOrder": 3
        },
        {
            "id": 101,
            "mediaType": 1,
            "rect": "584,200,1329,752",
            "backImage": None,
            "md5": None,
            "backColor": None,
            "params": {
                "video": {
                    "liveChannel": "",
                    "liveChannelName": "",
                    "media": [
                        {
                            "fileName": "http://172.25.10.146:9001/pids-fastdfs/fastdfs/preview-fastDFS?groupName=group1&filePath=M00/00/12/rBkKkmklE5KEBsYjAAAAALzr668881.mp4",
                            "md5": "3a11c9a7f10dbe4573c07afcd796566c"
                        }
                    ]
                },
                "volume": "20,20",
                "play": "0",
                "isProgram": 0
            },
            "zOrder": 2
        },
        {
            "id": 301,
            "mediaType": 3,
            "rect": "276,960,1632,96",
            "backImage": None,
            "md5": None,
            "backColor": None,
            "params": {
                "text": {
                    "contentCh": [
                        "欢迎乘坐济南轨道交通济阳线！"
                    ],
                    "fontCh": {
                        "name": "黑体",
                        "size": 72,
                        "bold": True,
                        "italic": None,
                        "textColor": "#FFFFFF",
                        "align": 2,
                        "effect": 0
                    },
                    "fontEn": None,
                    "contentEn": None,
                    "rectCh": None,
                    "rectEn": None
                },
                "speed": 60,
                "textdirection": 0,
                "isEmer": 0,
                "isProgram": None
            },
            "zOrder": 1
        },
        {
            "id": 601,
            "mediaType": 6,
            "rect": "11,11,563,938",
            "backImage": None,
            "md5": None,
            "backColor": None,
            "params": {
                "atsType": 0,
                "ats": {
                    "train1": generate_train_data("济阳北", "即将进站", "3"),
                    "train2": generate_empty_train_data(),
                    "train3": generate_empty_train_data()
                }
            },
            "zOrder": 3
        },
        {
            "id": 302,
            "mediaType": 3,
            "rect": "251,957,1657,113",
            "backImage": None,
            "md5": None,
            "backColor": None,
            "params": {
                "text": {
                    "contentCh": None,
                    "fontCh": {
                        "name": "黑体",
                        "size": 72,
                        "bold": None,
                        "italic": None,
                        "textColor": "#F44336",
                        "align": 0,
                        "effect": 0
                    },
                    "fontEn": None,
                    "contentEn": None,
                    "rectCh": None,
                    "rectEn": None
                },
                "speed": 66,
                "textdirection": None,
                "isEmer": 1,
                "isProgram": 0
            },
            "zOrder": 1
        }
    ]

def generate_double_trans_partitions():
    """生成双列车版式的partitions"""
    partitions = generate_single_trans_partitions()
    # 修改ATS分区为双列车
    for p in partitions:
        if p["id"] == 601:
            p["params"]["ats"]["train1"] = generate_train_data("崔寨", "即将进站", "")
            p["params"]["ats"]["train2"] = generate_train_data("崔寨", " ", "7")
    return partitions

def generate_train_data(dest, status, time_val):
    """生成列车数据"""
    return {
        "destCh": {
            "rect": "10,10,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "content": {
                "rect": "121,338,304,92",
                "text": dest,
                "font": {
                    "name": "黑体",
                    "size": 64,
                    "bold": True,
                    "italic": False,
                    "textColor": "#000000",
                    "align": 2,
                    "effect": 0
                }
            }
        },
        "destEn": {
            "rect": "10,50,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "content": {
                "rect": "150,50,130,30",
                "text": "",
                "font": {
                    "name": "微软雅黑",
                    "size": 12,
                    "bold": False,
                    "italic": False,
                    "textColor": None,
                    "align": 1,
                    "effect": 0
                }
            }
        },
        "nextCh": {
            "rect": "10,290,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "content": {
                "rect": "150,210,130,30",
                "text": "",
                "font": {
                    "name": "微软雅黑",
                    "size": 12,
                    "bold": False,
                    "italic": False,
                    "textColor": None,
                    "align": 1,
                    "effect": 0
                }
            }
        },
        "nextEn": {
            "rect": "150,250,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "content": {
                "rect": "10,250,130,30",
                "text": "",
                "font": {
                    "name": "微软雅黑",
                    "size": 12,
                    "bold": False,
                    "italic": False,
                    "textColor": None,
                    "align": 1,
                    "effect": 0
                }
            }
        },
        "skipCh": {
            "rect": "10,450,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "content": {
                "rect": "150,370,130,30",
                "text": "",
                "font": {
                    "name": "微软雅黑",
                    "size": 12,
                    "bold": False,
                    "italic": False,
                    "textColor": None,
                    "align": 1,
                    "effect": 0
                }
            }
        },
        "skipEn": {
            "rect": "150,400,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "content": {
                "rect": "10,400,130,30",
                "text": "",
                "font": {
                    "name": "微软雅黑",
                    "size": 12,
                    "bold": False,
                    "italic": False,
                    "textColor": None,
                    "align": 1,
                    "effect": 0
                }
            }
        },
        "trainTipCh": {
            "rect": "10,90,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "trainTipContent": {
                "status": {
                    "rect": "46,139,471,113",
                    "text": status,
                    "font": {
                        "name": "黑体",
                        "size": 72,
                        "bold": True,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 2,
                        "effect": 0
                    }
                },
                "time": {
                    "rect": "137,108,197,201",
                    "text": time_val,
                    "font": {
                        "name": "黑体",
                        "size": 150,
                        "bold": True,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 2,
                        "effect": 0
                    }
                },
                "min": {
                    "rect": "373,252,105,57",
                    "text": "分钟" if time_val else "",
                    "font": {
                        "name": "黑体",
                        "size": 36,
                        "bold": True,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 2,
                        "effect": 0
                    }
                },
                "group": {
                    "rect": "10,370,130,30",
                    "text": "",
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                },
                "trainType": {
                    "rect": "150,290,130,30",
                    "text": "",
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                }
            }
        },
        "trainTipEn": {
            "rect": "10,130,130,30",
            "tip": "",
            "font": {
                "name": "微软雅黑",
                "size": 12,
                "bold": False,
                "italic": False,
                "textColor": None,
                "align": 1,
                "effect": 0
            },
            "trainTipContent": {
                "status": {
                    "rect": "10,210,130,30",
                    "text": "",
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                },
                "time": {
                    "rect": "137,108,197,201",
                    "text": time_val,
                    "font": {
                        "name": "黑体",
                        "size": 150,
                        "bold": True,
                        "italic": False,
                        "textColor": "#000000",
                        "align": 2,
                        "effect": 0
                    }
                },
                "min": {
                    "rect": "150,130,130,30",
                    "text": "",
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                },
                "group": {
                    "rect": "150,320,130,30",
                    "text": "",
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                },
                "trainType": {
                    "rect": "10,320,130,30",
                    "text": "",
                    "font": {
                        "name": "微软雅黑",
                        "size": 12,
                        "bold": False,
                        "italic": False,
                        "textColor": None,
                        "align": 1,
                        "effect": 0
                    }
                }
            }
        }
    }

def generate_empty_train_data():
    """生成空的列车数据（用于train2, train3无数据时）"""
    return {
        "destCh": {"rect": None, "tip": None, "font": None, "content": None},
        "destEn": {"rect": None, "tip": None, "font": None, "content": None},
        "nextCh": {"rect": None, "tip": None, "font": None, "content": None},
        "nextEn": {"rect": None, "tip": None, "font": None, "content": None},
        "skipCh": {"rect": None, "tip": None, "font": None, "content": None},
        "skipEn": {"rect": None, "tip": None, "font": None, "content": None},
        "trainTipCh": {"rect": None, "tip": None, "font": None, "trainTipContent": None},
        "trainTipEn": {"rect": None, "tip": None, "font": None, "trainTipContent": None}
    }

def validate_field(value, field_name, required=True):
    """验证字段"""
    if value is None or value == '':
        if required:
            return False, f"缺少必填字段: {field_name}"
        return True, None
    return True, None

# ========================
# 任务管理接口（辅助接口）
# ========================

@app.route('/add_schedule_task', methods=['GET'])
def create_schedule_task():
    """
    创建播放计划任务
    参数:
      - metro: 线路编号
      - schedule_id: 播放计划ID（可选，默认自动生成）
      - name: 播放计划名称（可选）
      - device_list: 设备列表，逗号分隔（可选，默认使用 S00000001040,S00000001042）
    """
    metro_id = request.args.get('metro', CONFIG['default_metro'])
    schedule_id = request.args.get('schedule_id', seq_manager.next_task_id())
    name = request.args.get('name', f'站厅播出组{schedule_id}')
    device_list_str = request.args.get('device_list', '')

    # 解析设备列表
    device_list = [d.strip() for d in device_list_str.split(',') if d.strip()]

    # 生成播放计划
    schedule_data = generate_schedule({
        'id': schedule_id,
        'name': name,
        'startTime': datetime.datetime.now().strftime("%Y-%m-%d 08:00:00"),
        'endTime': (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d 20:00:00"),
        'weekFlag': '1,2,3,4,5,6,7',
        'level': 0
    })

    # 存储播放计划和关联任务
    data_store.add_schedule_with_layouts(schedule_id, metro_id, schedule_data, device_list)

    # 关联任务URL
    task_url = f"http://*.*.*.*:{CONFIG['port']}/mpis-intercut/api/play/schedules/taskId?taskId={schedule_id}"

    # 获取实际存储的设备列表
    stored_devices = data_store.tasks.get(int(schedule_id), {}).get('deviceList', [])

    log(f" 创建播放计划任务: taskId={schedule_id}, name={name}, metro={metro_id}, devices={len(stored_devices)}")

    return jsonify({
        "code": 0,
        "msg": "success",
        "taskId": schedule_id,
        "msgId": schedule_data['id'],
        "taskUrl": task_url,
        "deviceList": stored_devices,
        "deviceCount": len(stored_devices)
    }), 200

@app.route('/add_emergency_task', methods=['GET'])
def create_emergency_task():
    """
    创建紧急信息发布任务
    参数:
      - metro: 线路编号
      - task_id: 任务ID（可选，默认自动生成）
      - level: 级别 6-10全屏/1-5滚动（默认10）
      - content: 内容（可选，默认测试内容）
      - device_list: 设备列表，逗号分隔（可选）
    """
    metro_id = request.args.get('metro', CONFIG['default_metro'])
    task_id = request.args.get('task_id', seq_manager.next_task_id())
    level = int(request.args.get('level', 10))
    content = request.args.get('content', '测试紧急信息内容')
    device_list_str = request.args.get('device_list', 'S000000010301,S000000010302')

    device_list = [d.strip() for d in device_list_str.split(',') if d.strip()]

    # 生成紧急信息
    emer_data = generate_emergency(level, content)

    # 构建完整任务数据
    task_data = {
        "msgId": emer_data['msgId'],
        "levels": emer_data['levels'],
        "content": emer_data['content'],
        "createTime": emer_data['createTime'],
        "startTime": emer_data['startTime'],
        "endTime": emer_data['endTime']
    }

    # 存储（传递设备列表，add_emergency内部会处理默认值）
    data_store.add_emergency(task_id, metro_id, task_data, device_list)

    # 获取实际存储的设备列表
    stored_devices = data_store.tasks.get(int(task_id), {}).get('deviceList', [])

    log(f" 创建紧急信息任务: taskId={task_id}, level={level}, content={content[:20]}..., metro={metro_id}, devices={len(stored_devices)}")

    return jsonify({
        "code": 0,
        "msg": "success",
        "taskId": task_id,
        "msgId": emer_data['msgId'],
        "deviceList": stored_devices,
        "deviceCount": len(stored_devices)
    }), 200

@app.route('/add_cancel_task', methods=['GET'])
def create_cancel_task():
    """
    创建紧急信息撤销任务
    参数:
      - metro: 线路编号
      - task_id: 任务ID（可选，默认自动生成）
      - msg_id: 要撤销的消息ID（必填）
      - device_list: 设备列表（可选）
    """
    metro_id = request.args.get('metro', CONFIG['default_metro'])
    task_id = request.args.get('task_id', seq_manager.next_task_id())
    msg_id = request.args.get('msg_id')
    device_list_str = request.args.get('device_list', 'S000000010301,S000000010302')

    if not msg_id:
        return jsonify({"error": "缺少必填参数: msg_id"}), 400

    device_list = [d.strip() for d in device_list_str.split(',') if d.strip()]

    # 存储撤销任务
    data_store.add_cancel(task_id, metro_id, msg_id)

    log(f"✅ 创建撤销任务: taskId={task_id}, msgId={msg_id}, metro={metro_id}")

    return jsonify({
        "code": 0,
        "msg": "success",
        "taskId": task_id,
        "msgId": msg_id
    }), 200

@app.route('/add_device_control_task', methods=['GET'])
def create_device_control_task():
    """
    创建设备控制任务
    参数:
      - metro: 线路编号
      - cmd_type: 命令类型 03重启/04音量/05关声/06开声/07开屏/08关屏
      - task_id: 任务ID（可选）
      - left_sound: 左声道音量（cmd_type=04时必填）
      - right_sound: 右声道音量（cmd_type=04时必填）
      - port: 屏幕端口（cmd_type=07/08时必填）
      - device_list: 设备列表（可选）
    """
    metro_id = request.args.get('metro', CONFIG['default_metro'])
    cmd_type = request.args.get('cmd_type', '03')
    task_id = request.args.get('task_id', seq_manager.next_task_id())
    left_sound = request.args.get('left_sound', '50')
    right_sound = request.args.get('right_sound', '50')
    port = request.args.get('port', '01')
    device_list_str = request.args.get('device_list', 'S000000010301,S000000010302')

    device_list = [d.strip() for d in device_list_str.split(',') if d.strip()]

    # 参数校验
    if cmd_type == '04':
        if not left_sound or not right_sound:
            return jsonify({"error": "cmd_type=04需要指定left_sound和right_sound"}), 400
    if cmd_type in ['07', '08']:
        if not port:
            return jsonify({"error": "cmd_type=07/08需要指定port"}), 400

    # 生成控制数据
    ctrl_data = generate_control(cmd_type, device_list, {
        'leftSound': int(left_sound),
        'rightSound': int(right_sound),
        'port': port
    })

    # 存储
    data_store.add_control(task_id, metro_id, ctrl_data)

    log(f"✅ 创建设备控制任务: taskId={task_id}, cmdType={cmd_type}, metro={metro_id}")

    return jsonify({
        "code": 0,
        "msg": "success",
        "taskId": task_id,
        "msgId": seq_manager.next_msg_id()
    }), 200

@app.route('/delete_task', methods=['GET'])
def delete_task():
    """删除任务"""
    task_id = request.args.get('taskId')
    task_type = request.args.get('type')  # schedule, emergency, control

    if not task_id:
        return jsonify({"error": "缺少必填参数: taskId"}), 400

    # 统一转换为int类型，确保与存储时的key类型一致
    task_id = int(task_id)

    deleted = False

    if task_type in [None, 'schedule']:
        if task_id in data_store.schedules:
            del data_store.schedules[task_id]
            deleted = True
    if task_type in [None, 'emergency']:
        if task_id in data_store.emergencies:
            del data_store.emergencies[task_id]
            deleted = True
    if task_type in [None, 'control']:
        if task_id in data_store.controls:
            del data_store.controls[task_id]
            deleted = True
    if task_type in [None, 'all']:
        if task_id in data_store.tasks:
            del data_store.tasks[task_id]
            deleted = True

    if deleted:
        log(f"🗑️ 删除任务: taskId={task_id}")
        return jsonify({"code": 0, "msg": "success"}), 200
    else:
        return jsonify({"code": 1, "msg": "任务不存在"}), 404

@app.route('/clear_all_tasks', methods=['GET'])
def clear_all_tasks():
    """清空所有任务"""
    data_store.clear_all()
    log("🧹 清空所有任务")
    return jsonify({"code": 0, "msg": "success"}), 200

@app.route('/reset_sequence', methods=['GET'])
def reset_sequence():
    """重置序号计数器"""
    seq_manager.reset()
    log("🔢 重置序号计数器")
    return jsonify({"code": 0, "msg": "success"}), 200

# ========================
# 获取类接口（PIDS←PCC）
# ========================

@app.route('/mpis-intercut/api/task/cmd/metro', methods=['GET'])
def get_task_list():
    """
    任务命令获取
    PIDS调用此接口获取待处理的任务列表

    参数:
      - metro: 线路编号

    返回:
      - taskType: 1=紧急信息发布, 3=紧急信息撤销, 10=播放计划, 51=设备控制
    """
    metro_id = request.args.get('metro', CONFIG['default_metro'])

    if not metro_id:
        return jsonify({"error": "缺少必填参数: metro"}), 400

    # 收集该线路的所有任务
    task_list = []

    # 添加播放计划任务
    for task_id, schedule in data_store.schedules.items():
        task_url = f"http://*.*.*.*:{CONFIG['port']}/mpis-intercut/api/play/schedules/taskId?taskId={task_id}"
        task_list.append({
            "taskType": 10,
            "taskId": str(task_id),
            "taskUrl": task_url,
            "updatedTime": schedule.get('updatedTime', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "deviceList": data_store.tasks.get(task_id, {}).get('deviceList', [])
        })

    # 添加紧急信息发布任务
    for task_id, emer in data_store.emergencies.items():
        task_url = f"http://*.*.*.*:{CONFIG['port']}/mpis-intercut/api/operate/emer/taskId?taskId={task_id}"
        task_list.append({
            "taskType": 1,
            "taskId": str(task_id),
            "taskUrl": task_url,
            "updatedTime": emer.get('createTime', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "deviceList": data_store.tasks.get(task_id, {}).get('deviceList', [])
        })

    # 添加设备控制任务
    for task_id, ctrl in data_store.controls.items():
        task_url = f"http://*.*.*.*:{CONFIG['port']}/mpis-intercut/api/ctrl/devicectrl/taskId?taskId={task_id}"
        task_list.append({
            "taskType": 51,
            "taskId": str(task_id),
            "taskUrl": task_url,
            "updatedTime": ctrl.get('createTime', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "deviceList": ctrl.get('deviceList', [])
        })

    # 添加撤销任务
    for task_id, task in data_store.tasks.items():
        if task.get('taskType') == '3':
            task_url = f"http://*.*.*.*:{CONFIG['port']}/mpis-intercut/api/operate/emer/taskId?taskId={task_id}"
            task_list.append({
                "taskType": 3,
                "taskId": str(task_id),
                "taskUrl": task_url,
                "updatedTime": task.get('updatedTime', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "deviceList": task.get('deviceList', [])
            })

    log(f"📋 任务列表获取: metro={metro_id}, 任务数={len(task_list)}")

    return jsonify({"task": task_list}), 200

@app.route('/mpis-intercut/api/play/schedules/taskId', methods=['GET'])
def get_schedule():
    """
    播放计划获取
    PIDS获取播放计划的详细信息，包括关联的版式列表

    参数:
      - taskId: 播放计划ID
    """
    task_id = request.args.get('taskId')

    if not task_id:
        return jsonify({"error": "缺少必填参数: taskId"}), 400

    # 统一转换为int类型，确保与存储时的key类型一致
    task_id = int(task_id)
    schedule = data_store.schedules.get(task_id)

    if not schedule:
        return jsonify({"error": "播放计划不存在"}), 404

    log(f"📋 播放计划获取: taskId={task_id}")

    return jsonify(schedule), 200

@app.route('/mpis-intercut/api/play/schedules/layout', methods=['GET'])
def get_layout():
    """
    版式获取
    PIDS获取版式的详细信息

    参数:
      - layout: 版式ID
    """
    layout_id = request.args.get('layout')

    if not layout_id:
        return jsonify({"error": "缺少必填参数: layout"}), 400

    # 统一转换为int类型，确保与存储时的key类型一致
    layout_id = int(layout_id)
    layout = data_store.layouts.get(layout_id)

    if not layout:
        # 如果版式不存在，生成一个默认版式
        layout = generate_layout({'id': layout_id})
        data_store.layouts[layout_id] = layout

    log(f"🎨 版式获取: layout={layout_id}")

    return jsonify(layout), 200

@app.route('/mpis-intercut/api/operate/emer/taskId', methods=['GET'])
def get_emergency():
    """
    紧急信息获取
    PIDS获取紧急信息的详细信息

    参数:
      - taskId: 任务ID
    """
    task_id = request.args.get('taskId')

    if not task_id:
        return jsonify({"error": "缺少必填参数: taskId"}), 400

    # 统一转换为int类型，确保与存储时的key类型一致
    task_id = int(task_id)

    # 检查是否是撤销任务
    task_info = data_store.tasks.get(task_id, {})

    if task_info.get('taskType') == '3':
        # 撤销任务
        log(f"🚫 紧急撤销获取: taskId={task_id}, msgId={task_info.get('msgId')}")
        return jsonify({
            "cmdType": 1,
            "emer": [
                {"msgId": task_info.get('msgId', '')}
            ]
        }), 200

    # 紧急发布任务
    emer = data_store.emergencies.get(task_id)

    if not emer:
        return jsonify({"error": "紧急信息不存在"}), 404

    log(f"🚨 紧急信息获取: taskId={task_id}, level={emer.get('levels')}")

    return jsonify({
        "emer": [emer]
    }), 200

@app.route('/mpis-intercut/api/ctrl/devicectrl/taskId', methods=['GET'])
def get_device_control():
    """
    设备控制指令获取
    PIDS获取设备控制指令的详细信息

    参数:
      - taskId: 任务ID
    """
    task_id = request.args.get('taskId')

    if not task_id:
        return jsonify({"error": "缺少必填参数: taskId"}), 400

    ctrl = data_store.controls.get(task_id)

    if not ctrl:
        return jsonify({"error": "设备控制任务不存在"}), 404

    log(f"🎮 设备控制获取: taskId={task_id}, cmdType={ctrl.get('cmdType')}")

    return jsonify({
        "ctrlCmd": [ctrl]
    }), 200

# ========================
# 回传类接口（PIDS→PCC）
# ========================

@app.route('/mpis-intercut/api/ats/atsInfo/metro', methods=['POST'])
def receive_ats_info():
    """
    ATS信息接入
    PIDS推送ATS列车信息给PCC

    必填字段校验:
      - lineId: 线路ID
      - stationId: 车站ID
      - atsInfo: 列车信息数组
        - stationId: 站台ID
        - direction: 方向（1=上行/2=下行）
        - platformId: 站台编号
        - trainCode: 列车编号
        - arrivalTime: 到站时间
        - departureTime: 离站时间
        - status: 状态（0未知/1即将进站/2到站/3离站）
        - holdFlag: 扣车标识
        - skipFlag: 跳站标识
        - outOfService: 不载客标识
        - lastTrain: 首末班标识
    """
    metro_id = request.args.get('metro')

    if not metro_id:
        return jsonify({"error": "缺少必填参数: metro"}), 400

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空或JSON格式错误"}), 400
    except Exception as e:
        return jsonify({"error": f"JSON解析失败: {str(e)}"}), 400

    # 验证必填字段
    errors = []

    if 'lineId' not in data or not data['lineId']:
        errors.append("缺少必填字段: lineId")

    if 'stationId' not in data or not data['stationId']:
        errors.append("缺少必填字段: stationId")

    if 'atsInfo' not in data:
        errors.append("缺少必填字段: atsInfo")
    elif data['atsInfo'] is None:
        errors.append("atsInfo不能为null")
    elif not isinstance(data['atsInfo'], list):
        errors.append("atsInfo必须是数组")
    else:
        # 验证每个列车信息
        for idx, ats in enumerate(data['atsInfo']):
            if not isinstance(ats, dict):
                errors.append(f"atsInfo[{idx}]必须是对象")
                continue

            required_train_fields = ['stationId', 'direction', 'platformId', 'trainCode', 'arrivalTime', 'departureTime', 'status']
            for field in required_train_fields:
                if field not in ats or ats[field] is None or ats[field] == '':
                    errors.append(f"atsInfo[{idx}]缺少必填字段: {field}")

            # 验证status范围
            if 'status' in ats:
                try:
                    status = int(ats['status'])
                    if status < 0 or status > 3:
                        errors.append(f"atsInfo[{idx}]status值必须在0-3范围内，当前值: {status}")
                except (ValueError, TypeError):
                    errors.append(f"atsInfo[{idx}]status必须是数字")

    if errors:
        error_msg = "; ".join(errors)
        log(f"❌ ATS信息校验失败: {error_msg}")
        return jsonify({"error": error_msg}), 400

    # 存储接收到的数据
    data_store.received_ats.append({
        "receivedTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metro": metro_id,
        "data": data
    })

    log(f"✅ ATS信息接收成功: metro={metro_id}, 车站={data.get('stationId')}, 列车数={len(data.get('atsInfo', []))}")

    return jsonify({"code": 0, "msg": "success"}), 200

@app.route('/mpis-intercut/api/devicemonitor/metro', methods=['POST'])
@app.route('/mpis-intercut/api/deviceMonitor/metro', methods=['POST'])
def receive_device_status():
    """
    设备状态监测接入
    PIDS推送设备状态给PCC

    必填字段校验:
      - updatedTime: 更新时间
      - lineCode: 线路编号
      - deviceList: 设备列表
        - code: 设备编号
        - status: 状态列表
          - field: 字段名称
          - fieldType: 字段类型
          - value: 字段值
        - alarm: 告警列表（可选）
          - fieldId: 告警编码
          - levels: 告警等级
          - reason: 告警原因
    """
    metro_id = request.args.get('metro')

    if not metro_id:
        return jsonify({"error": "缺少必填参数: metro"}), 400

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空或JSON格式错误"}), 400
    except Exception as e:
        return jsonify({"error": f"JSON解析失败: {str(e)}"}), 400

    # 验证必填字段
    errors = []

    if 'updatedTime' not in data or not data['updatedTime']:
        errors.append("缺少必填字段: updatedTime")

    if 'lineCode' not in data or not data['lineCode']:
        errors.append("缺少必填字段: lineCode")

    if 'deviceList' not in data:
        errors.append("缺少必填字段: deviceList")
    elif not isinstance(data['deviceList'], list):
        errors.append("deviceList必须是数组")
    else:
        # 验证每个设备
        for idx, device in enumerate(data['deviceList']):
            if not isinstance(device, dict):
                errors.append(f"deviceList[{idx}]必须是对象")
                continue

            if 'code' not in device or not device['code']:
                errors.append(f"deviceList[{idx}]缺少必填字段: code")

            if 'status' in device:
                if not isinstance(device['status'], list):
                    errors.append(f"deviceList[{idx}].status必须是数组")
                else:
                    for sidx, status in enumerate(device['status']):
                        if not isinstance(status, dict):
                            errors.append(f"deviceList[{idx}].status[{sidx}]必须是对象")
                            continue
                        if 'fieldType' not in status:
                            errors.append(f"deviceList[{idx}].status[{sidx}]缺少必填字段: fieldType")

            # 验证告警
            if 'alarm' in device:
                if not isinstance(device['alarm'], list):
                    errors.append(f"deviceList[{idx}].alarm必须是数组")
                else:
                    for aidx, alarm in enumerate(device['alarm']):
                        if not isinstance(alarm, dict):
                            errors.append(f"deviceList[{idx}].alarm[{aidx}]必须是对象")
                            continue
                        if 'fieldId' not in alarm:
                            errors.append(f"deviceList[{idx}].alarm[{aidx}]缺少必填字段: fieldId")
                        if 'levels' not in alarm:
                            errors.append(f"deviceList[{idx}].alarm[{aidx}]缺少必填字段: levels")
                        if 'reason' not in alarm:
                            errors.append(f"deviceList[{idx}].alarm[{aidx}]缺少必填字段: reason")

    if errors:
        error_msg = "; ".join(errors)
        log(f"❌ 设备状态校验失败: {error_msg}")
        return jsonify({"error": error_msg}), 400

    # 存储接收到的数据
    data_store.received_device_status.append({
        "receivedTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metro": metro_id,
        "data": data
    })

    device_count = len(data.get('deviceList', []))
    log(f"✅ 设备状态接收成功: metro={metro_id}, 设备数={device_count}")

    return jsonify({"code": 0, "msg": "success"}), 200

@app.route('/mpis-intercut/api/monitor/task/metro', methods=['POST'])
def receive_task_feedback():
    """
    设备任务状态反馈
    PIDS推送任务执行结果给PCC

    必填字段校验:
      - updatedTime: 更新时间
      - lineCode: 线路编号
      - deviceList: 设备列表
        - {deviceId}: 设备ID（动态key）
          - taskID: 任务ID
          - retType: 回传类型（01=执行进度, 02=执行结果）
          - result: 执行结果（1=成功, 2=失败）
    """
    metro_id = request.args.get('metro')

    if not metro_id:
        return jsonify({"error": "缺少必填参数: metro"}), 400

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空或JSON格式错误"}), 400
    except Exception as e:
        return jsonify({"error": f"JSON解析失败: {str(e)}"}), 400

    # 验证必填字段
    errors = []

    if 'updatedTime' not in data or not data['updatedTime']:
        errors.append("缺少必填字段: updatedTime")

    if 'lineCode' not in data or not data['lineCode']:
        errors.append("缺少必填字段: lineCode")

    if 'deviceList' not in data:
        errors.append("缺少必填字段: deviceList")
    elif not isinstance(data['deviceList'], list):
        errors.append("deviceList必须是数组")
    else:
        # 验证每个设备反馈
        for idx, device in enumerate(data['deviceList']):
            if not isinstance(device, dict):
                errors.append(f"deviceList[{idx}]必须是对象")
                continue

            # deviceList的结构是 {deviceId: [feedback]}
            for device_id, feedbacks in device.items():
                if not feedbacks or not isinstance(feedbacks, list):
                    errors.append(f"deviceList[{idx}]的设备{device_id}反馈数据格式错误")
                    continue

                for fidx, feedback in enumerate(feedbacks):
                    if not isinstance(feedback, dict):
                        errors.append(f"设备{device_id}反馈[{fidx}]必须是对象")
                        continue

                    if 'taskID' not in feedback:
                        errors.append(f"设备{device_id}反馈[{fidx}]缺少必填字段: taskID")
                    if 'retType' not in feedback:
                        errors.append(f"设备{device_id}反馈[{fidx}]缺少必填字段: retType")
                    if 'result' not in feedback:
                        errors.append(f"设备{device_id}反馈[{fidx}]缺少必填字段: result")

    if errors:
        error_msg = "; ".join(errors)
        log(f"❌ 任务反馈校验失败: {error_msg}")
        return jsonify({"error": error_msg}), 400

    # 存储接收到的数据
    data_store.received_monitor.append({
        "receivedTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metro": metro_id,
        "data": data
    })

    device_count = len(data.get('deviceList', []))
    log(f"✅ 任务反馈接收成功: metro={metro_id}, 设备数={device_count}")

    return jsonify({"code": 0, "msg": "success"}), 200

# ========================
# Web管理界面
# ========================

@app.route('/')
def index():
    """管理首页"""
    # 统计
    stats = {
        'schedules': len(data_store.schedules),
        'emergencies': len(data_store.emergencies),
        'controls': len(data_store.controls),
        'layouts': len(data_store.layouts),
        'tasks': len(data_store.tasks),
        'received_ats': len(data_store.received_ats),
        'received_monitor': len(data_store.received_monitor),
        'received_device_status': len(data_store.received_device_status)
    }

    # 最近接收的回传数据
    recent_ats = data_store.received_ats[-5:] if data_store.received_ats else []
    recent_monitor = data_store.received_monitor[-5:] if data_store.received_monitor else []
    recent_device_status = data_store.received_device_status[-5:] if data_store.received_device_status else []

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PCC Mock Server v2.0</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; margin-bottom: 20px; text-align: center; }}
        .card {{ background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
        .stat {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat.green {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }}
        .stat.orange {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }}
        .stat.blue {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
        .stat-number {{ font-size: 32px; font-weight: bold; }}
        .stat-label {{ font-size: 14px; opacity: 0.9; margin-top: 5px; }}
        h2 {{ color: #333; margin-bottom: 15px; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
        .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px; }}
        .form-section {{ background: #f9f9f9; padding: 15px; border-radius: 6px; }}
        .form-section h3 {{ margin-bottom: 10px; color: #555; font-size: 14px; }}
        .form-row {{ display: flex; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }}
        .form-row input {{ flex: 1; min-width: 100px; padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }}
        .form-row button {{ padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer; transition: background 0.3s; }}
        .form-row button:hover {{ background: #764ba2; }}
        .btn-secondary {{ background: #6c757d !important; }}
        .btn-danger {{ background: #dc3545 !important; }}
        .btn-success {{ background: #28a745 !important; }}
        .info {{ background: #e7f3ff; padding: 15px; border-radius: 6px; margin-top: 20px; }}
        .info h4 {{ margin-bottom: 10px; }}
        .received-list {{ max-height: 200px; overflow-y: auto; }}
        .received-item {{ background: #f9f9f9; padding: 8px; margin-bottom: 5px; border-radius: 4px; font-size: 12px; border-left: 3px solid #667eea; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f5f5f5; font-weight: 600; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PCC Mock Server v2.0 - 济南轨道交通</h1>

        <div class="card">
            <div class="stats">
                <div class="stat">
                    <div class="stat-number">{stats['schedules']}</div>
                    <div class="stat-label">播放计划</div>
                </div>
                <div class="stat green">
                    <div class="stat-number">{stats['emergencies']}</div>
                    <div class="stat-label">紧急信息</div>
                </div>
                <div class="stat orange">
                    <div class="stat-number">{stats['controls']}</div>
                    <div class="stat-label">设备控制</div>
                </div>
                <div class="stat blue">
                    <div class="stat-number">{stats['layouts']}</div>
                    <div class="stat-label">版式</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>任务创建</h2>
            <div class="form-grid">
                <div class="form-section">
                    <h3>创建播放计划任务</h3>
                    <form action="/add_schedule_task" method="GET">
                        <div class="form-row">
                            <input type="text" name="metro" value="{CONFIG['default_metro']}" placeholder="线路编号">
                            <input type="text" name="schedule_id" placeholder="计划ID(可选)">
                            <button type="submit">创建</button>
                        </div>
                        <div class="form-row">
                            <input type="text" name="name" placeholder="计划名称(可选)">
                        </div>
                    </form>
                </div>

                <div class="form-section">
                    <h3>创建紧急信息任务</h3>
                    <form action="/add_emergency_task" method="GET">
                        <div class="form-row">
                            <input type="text" name="metro" value="{CONFIG['default_metro']}" placeholder="线路编号">
                            <input type="text" name="level" value="10" placeholder="级别(6-10全屏/1-5滚动)">
                        </div>
                        <div class="form-row">
                            <input type="text" name="content" placeholder="内容(可选)">
                            <button type="submit">创建</button>
                        </div>
                    </form>
                </div>

                <div class="form-section">
                    <h3>创建撤销任务</h3>
                    <form action="/add_cancel_task" method="GET">
                        <div class="form-row">
                            <input type="text" name="metro" value="{CONFIG['default_metro']}" placeholder="线路编号">
                            <input type="text" name="msg_id" placeholder="要撤销的msgId(必填)">
                        </div>
                        <div class="form-row">
                            <button type="submit">创建</button>
                        </div>
                    </form>
                </div>

                <div class="form-section">
                    <h3>创建设备控制任务</h3>
                    <form action="/add_device_control_task" method="GET">
                        <div class="form-row">
                            <input type="text" name="metro" value="{CONFIG['default_metro']}" placeholder="线路编号">
                            <select name="cmd_type" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                                <option value="03">03-设备重启</option>
                                <option value="04">04-声音调整</option>
                                <option value="05">05-关闭声音</option>
                                <option value="06">06-打开声音</option>
                                <option value="07">07-打开屏幕</option>
                                <option value="08">08-关闭屏幕</option>
                            </select>
                        </div>
                        <div class="form-row">
                            <input type="text" name="left_sound" placeholder="左声道(0-100)">
                            <input type="text" name="right_sound" placeholder="右声道(0-100)">
                        </div>
                        <div class="form-row">
                            <input type="text" name="port" placeholder="屏幕端口">
                            <button type="submit">创建</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>工具</h2>
            <div class="form-row">
                <form action="/reset_sequence" method="GET" style="display:inline;">
                    <button type="submit" class="btn-secondary">重置序号</button>
                </form>
                <form action="/clear_all_tasks" method="GET" style="display:inline;">
                    <button type="submit" class="btn-danger">清空所有任务</button>
                </form>
            </div>
        </div>

        <div class="card">
            <h2>已创建的任务</h2>
            <table>
                <thead>
                    <tr>
                        <th>类型</th>
                        <th>TaskId</th>
                        <th>名称/级别</th>
                        <th>设备数</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>"""

    # 添加播放计划
    for task_id, schedule in data_store.schedules.items():
        html += f"""<tr>
            <td>播放计划</td>
            <td>{task_id}</td>
            <td>{schedule.get('name', '')}</td>
            <td>{len(data_store.tasks.get(task_id, {}).get('deviceList', []))}</td>
            <td><form action="/delete_task" method="GET" style="display:inline;"><input type="hidden" name="taskId" value="{task_id}"><input type="hidden" name="type" value="schedule"><button type="submit" class="btn-danger" style="padding:2px 8px;font-size:11px;">删除</button></form></td>
        </tr>"""

    # 添加紧急信息
    for task_id, emer in data_store.emergencies.items():
        html += f"""<tr>
            <td>紧急信息</td>
            <td>{task_id}</td>
            <td>level={emer.get('levels')}</td>
            <td>{len(data_store.tasks.get(task_id, {}).get('deviceList', []))}</td>
            <td><form action="/delete_task" method="GET" style="display:inline;"><input type="hidden" name="taskId" value="{task_id}"><input type="hidden" name="type" value="emergency"><button type="submit" class="btn-danger" style="padding:2px 8px;font-size:11px;">删除</button></form></td>
        </tr>"""

    # 添加设备控制
    for task_id, ctrl in data_store.controls.items():
        html += f"""<tr>
            <td>设备控制</td>
            <td>{task_id}</td>
            <td>cmd={ctrl.get('cmdType')}</td>
            <td>{len(ctrl.get('deviceList', []))}</td>
            <td><form action="/delete_task" method="GET" style="display:inline;"><input type="hidden" name="taskId" value="{task_id}"><input type="hidden" name="type" value="control"><button type="submit" class="btn-danger" style="padding:2px 8px;font-size:11px;">删除</button></form></td>
        </tr>"""

    html += f"""</tbody>
            </table>
        </div>

        <div class="card">
            <h2>最近接收的ATS数据 ({len(recent_ats)}条)</h2>
            <div class="received-list">"""

    for item in recent_ats:
        html += f"""<div class="received-item">
            <strong>{item['receivedTime']}</strong> - 车站:{item['data'].get('stationId')} -
            列车:{len(item['data'].get('atsInfo', []))}趟
        </div>"""

    html += """</div>
        </div>

        <div class="card">
            <h2>最近接收的任务反馈 ({len(recent_monitor)}条)</h2>
            <div class="received-list">"""

    for item in recent_monitor:
        html += f"""<div class="received-item">
            <strong>{item['receivedTime']}</strong> - 线路:{item['data'].get('lineCode')} -
            设备:{len(item['data'].get('deviceList', []))}个
        </div>"""

    html += """</div>
        </div>

        <div class="card">
            <h2>最近接收的设备状态 ({len(recent_device_status)}条)</h2>
            <div class="received-list">"""

    for item in recent_device_status:
        html += f"""<div class="received-item">
            <strong>{item['receivedTime']}</strong> - 线路:{item['data'].get('lineCode')} -
            设备:{len(item['data'].get('deviceList', []))}个
        </div>"""

    html += f"""</div>
        </div>

        <div class="info">
            <h4>接口说明</h4>
            <p><strong>获取类接口(PIDS→PCC):</strong></p>
            <ul>
                <li>GET /mpis-intercut/api/task/cmd/metro?metro=20 - 获取任务列表</li>
                <li>GET /mpis-intercut/api/play/schedules/taskId?taskId=xxx - 获取播放计划</li>
                <li>GET /mpis-intercut/api/play/schedules/layout?layout=xxx - 获取版式</li>
                <li>GET /mpis-intercut/api/operate/emer/taskId?taskId=xxx - 获取紧急信息</li>
                <li>GET /mpis-intercut/api/ctrl/devicectrl/taskId?taskId=xxx - 获取设备控制</li>
            </ul>
            <p><strong>回传类接口(PCC→PIDS):</strong></p>
            <ul>
                <li>POST /mpis-intercut/api/ats/atsInfo/metro?metro=20 - ATS信息接入</li>
                <li>POST /mpis-intercut/api/devicemonitor/metro?metro=20 - 设备状态监测</li>
                <li>POST /mpis-intercut/api/monitor/task/metro?metro=20 - 设备任务反馈</li>
            </ul>
            <p><strong>当前时间:</strong> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>"""

    return html

# ========================
# 启动入口
# ========================

def print_routes():
    """打印路由信息"""
    print("\n" + "="*60)
    print("PCC Mock Server v2.0 - 济南轨道交通接口模拟")
    print("="*60)
    print("\n📌 获取类接口（PIDS→PCC）:")
    print("   GET  /mpis-intercut/api/task/cmd/metro           - 任务命令获取")
    print("   GET  /mpis-intercut/api/play/schedules/taskId    - 播放计划获取")
    print("   GET  /mpis-intercut/api/play/schedules/layout    - 版式获取")
    print("   GET  /mpis-intercut/api/operate/emer/taskId     - 紧急信息获取")
    print("   GET  /mpis-intercut/api/ctrl/devicectrl/taskId  - 设备控制获取")
    print("\n📌 回传类接口（PIDS←PCC）:")
    print("   POST /mpis-intercut/api/ats/atsInfo/metro        - ATS信息接入")
    print("   POST /mpis-intercut/api/devicemonitor/metro     - 设备状态监测")
    print("   POST /mpis-intercut/api/monitor/task/metro      - 任务状态反馈")
    print("\n📌 辅助管理接口:")
    print("   GET  /add_schedule_task      - 创建播放计划任务")
    print("   GET  /add_emergency_task    - 创建紧急信息任务")
    print("   GET  /add_cancel_task       - 创建撤销任务")
    print("   GET  /add_device_control_task - 创建设备控制任务")
    print("   GET  /delete_task           - 删除任务")
    print("   GET  /clear_all_tasks      - 清空所有任务")
    print("   GET  /reset_sequence        - 重置序号计数器")
    print("\n📌 Web界面: http://localhost:5000/")
    print("="*60 + "\n")

if __name__ == '__main__':
    print_routes()
    app.run(host='0.0.0.0', port=CONFIG['port'], debug=False)
