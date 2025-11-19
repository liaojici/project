swap_coin_system/
├── main.py # 主程序入口
├── run.py # 启动脚本
├── requirements.txt # 依赖包列表
├── .env.example # 环境变量示例
├── config/ # 配置文件
│ ├── settings.py # 环境设置
│ └── constants.py # 策略参数
├── core/ # 核心功能
│ ├── api_client.py # API客户端
│ ├── cache_manager.py # 缓存管理
│ └── state_manager.py # 状态管理
├── modules/ # 策略模块
│ ├── chain_analysis.py # 链上分析
│ ├── sentiment_analysis.py # 情绪分析
│ ├── technical_analysis.py # 技术分析
│ ├── symbol_selection.py # 标的筛选
│ ├── position_management.py # 仓位管理
│ └── trading_execution.py # 交易执行
└── utils/ # 工具函数
├── decorators.py # 装饰器
├── validators.py # 验证器
└── logger.py # 日志配置


## 安装说明

1. 克隆或下载项目文件
2. 安装依赖：
   ```bash
   pip install -r requirements.txt