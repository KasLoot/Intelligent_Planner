# ReFlow POI 数据库设计说明

## 1. 数据库概述

### 1.1 项目背景

ReFlow 是一个面向本地生活场景的实时 Recovery / Replanning Agent，用于处理餐饮、酒店、景点、Citywalk 等本地生活动态规划场景。

本数据库是为 AI Agent 提供 **可推理的场景空间数据**。

### 1.2 数据库目标

构建一个 **小型虚拟城市（Mock City）** 的地点数据库，用于 AI Agent Demo，支持：
- ✅ Recovery 推理（被动恢复）
- ✅ Replanning 推理（主动重规划）
- ✅ 动态替换链
- ✅ 空间关联网络

### 1.3 文件位置

```
/Reflow/poi_database.json
```

---

## 2. 城市结构

### 2.1 三大商圈（District）

| 商圈 ID | 商圈名称 | 地点数量 | 特色 |
|---------|---------|---------|------|
| `riverfront_leisure` | 江边休闲区 | 19 个 | 江景、休闲、户外 |
| `cdb_business` | CBD 商务区 | 15 个 | 商务、购物、白领 |
| `mall_entertainment` | 商场娱乐区 | 20 个 | 综合、娱乐、餐饮 |

**总计：54 个 POI 地点**

### 2.2 商圈特征

#### 江边休闲区（riverfront_leisure）
- **地理特征**：沿江分布，户外景点多
- **主要业态**：江景餐厅、咖啡馆、公园、观景台
- **适用场景**：Citywalk、情侣约会、日落观赏
- **Recovery 特点**：下雨天需要大量 indoor 替代方案

#### CBD 商务区（cbd_business）
- **地理特征**：高楼密集，室内空间多
- **主要业态**：商务餐厅、咖啡厅、购物中心、酒店
- **适用场景**：商务宴请、白领午餐、购物
- **Recovery 特点**：室内场所多，受天气影响小

#### 商场娱乐区（mall_entertainment）
- **地理特征**：综合体集中，功能齐全
- **主要业态**：大型商场、餐饮连锁、娱乐场所
- **适用场景**：家庭聚会、娱乐、一站式消费
- **Recovery 特点**：室内一体化，替代选择丰富

---

## 3. 数据结构

### 3.1 POI JSON 结构

每个 POI 包含以下字段：

```json
{
  "poi_id": "RB001",
  "poi_name": "川味观·滨江路店",
  "district": "riverfront_leisure",
  "category": "restaurant",
  "sub_category": "hotpot",
  "coordinates": {
    "x": "120.1987",
    "y": "30.2541"
  },
  "price_level": "medium",
  "average_cost": "120",
  "opening_hours": "11:00-22:00",
  "indoor_or_outdoor": "indoor",
  "stay_duration_minutes": "90",
  "crowd_level": "high",
  "service_speed": "medium",
  "transport_accessibility": "good",
  "tags": ["江景", "川菜", "聚餐"],
  "recovery_tags": ["budget_replacement", "group_friendly"],
  "suitable_for": ["晚餐", "朋友聚会", "情侣约会"],
  "unsuitable_for": ["快速用餐", "下雨天户外等待"],
  "replacement_candidates": ["RB015", "CB003", "MB007"],
  "nearby_pois": ["RB010", "RB011", "RB020"],
  "timeline_flexibility": "semi_flexible",
  "recovery_priority": "medium"
}
```

### 3.2 字段说明

#### 基础信息
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `poi_id` | string | POI 唯一标识（前缀表示商圈） | RB001, CB001, MB001 |
| `poi_name` | string | 地点真实名称 | 川味观·滨江路店 |
| `district` | string | 所属商圈 | riverfront_leisure |
| `category` | string | 主分类 | restaurant, hotel, attraction, mall, transport, entertainment, resting_area |
| `sub_category` | string | 子分类 | hotpot, cantonese, coffee, citywalk 等 |

#### 位置信息
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `coordinates.x` | string | 经度 | 120.1987 |
| `coordinates.y` | string | 纬度 | 30.2541 |

#### 价格与时间
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `price_level` | string | 价格档位 | low, medium, high |
| `average_cost` | string | 平均消费（元） | 120 |
| `opening_hours` | string | 营业时间 | 11:00-22:00, 24h |

#### 空间属性
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `indoor_or_outdoor` | string | 室内外属性 | indoor, outdoor, mixed |
| `stay_duration_minutes` | string | 建议停留时长（分钟） | 90 |

#### 服务特征
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `crowd_level` | string | 拥挤程度 | low, medium, high |
| `service_speed` | string | 服务速度 | fast, medium, slow |
| `transport_accessibility` | string | 交通便利性 | good, excellent, medium |

#### Recovery 核心字段
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `recovery_tags` | array | Recovery 推理标签 | rainy_day_friendly, indoor_backup |
| `replacement_candidates` | array | 可替换 POI ID 列表 | ["RB015", "CB003"] |
| `nearby_pois` | array | 附近 POI ID 列表 | ["RB010", "RB011"] |
| `timeline_flexibility` | string | 时间灵活性 | flexible, semi_flexible, fixed |
| `recovery_priority` | string | Recovery 优先级 | low, medium, high |

#### 场景标签
| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `tags` | array | 业务标签 | ["江景", "川菜", "聚餐"] |
| `suitable_for` | array | 适用场景 | ["晚餐", "朋友聚会"] |
| `unsuitable_for` | array | 不适用场景 | ["快速用餐", "下雨天"] |

---

## 4. Recovery Tags 体系

### 4.1 完整标签列表

| 标签 | 说明 | 适用场景 |
|------|------|----------|
| `rainy_day_friendly` | 下雨天友好 | 室内场所、有遮蔽 |
| `traffic_delay_friendly` | 交通延迟友好 | 地铁站附近、灵活时间 |
| `budget_replacement` | 预算可替换 | 价格相近的替代 |
| `fast_replacement` | 快速替换 | 立即可用的替代 |
| `quick_stop` | 短暂停留 | 休息、避雨、等人 |
| `queue_friendly` | 排队友好 | 可接受排队、叫号系统 |
| `late_night_available` | 深夜可用 | 营业到深夜 |
| `indoor_backup` | 室内备选 | outdoor 失效时替代 |
| `group_friendly` | 团体友好 | 适合多人聚会 |
| `walkable` | 步行可达 | 距离近、可步行 |
| `low_waiting_time` | 低等待时间 | 无需长时间排队 |

### 4.2 Recovery 推理示例

#### 场景 1：下雨天
```
触发条件：weather == "rainy"
过滤规则：排除 indoor_or_outdoor == "outdoor" 的 POI
优先选择：recovery_tags 包含 "rainy_day_friendly" 或 "indoor_backup"
示例推理：
  滨江公园 (outdoor) → 龙湖天街 (indoor_mall, rainy_day_friendly)
```

#### 场景 2：交通拥堵
```
触发条件：traffic == "congested"
过滤规则：排除跨商圈、transport_accessibility == "medium" 的 POI
优先选择：recovery_tags 包含 "traffic_delay_friendly" 或 "walkable"
示例推理：
  跨商圈火锅 → 同商圈粤菜 (walkable, same district)
```

#### 场景 3：预算调整
```
触发条件：user_says "换个便宜一点的"
过滤规则：price_level 降低一档
优先选择：recovery_tags 包含 "budget_replacement"
示例推理：
  火锅 (medium, 120元) → 面馆 (low, 35元, budget_replacement)
```

---

## 5. 替换链（Replacement Candidates）

### 5.1 设计原则

1. **同商圈优先**：优先推荐同一商圈内的替代
2. **步行可达**：保持距离可接受
3. **预算相近**：价格档位一致或略低
4. **品类相关**：同品类或相近品类

### 5.2 典型替换链

#### 火锅替换链
```
川味观·滨江路店 (hotpot, medium)
  ↓
渝味火锅店 (hotpot, medium) [同商圈]
  ↓
翠园·粤菜馆 (cantonese, high) [同商圈，品类切换]
  ↓
外婆家 (chinese, medium) [跨商圈，预算相近]
  ↓
麦当劳 (fast_food, low) [快速替代，低预算]
```

#### 咖啡替换链
```
江风咖啡·露台店 (coffee, low)
  ↓
星巴克臻选 (coffee, medium) [跨商圈，升级]
  ↓
漫咖啡 (cafe, medium) [同品类]
  ↓
喜茶 (tea_drink, medium) [饮品替代]
```

#### Citywalk 替换链
```
滨江公园 (outdoor, citywalk)
  ↓
江畔艺术展馆 (indoor, gallery) [下雨天替代]
  ↓
龙湖天街 (indoor_mall) [室内逛街]
  ↓
中央商务区步行街 (outdoor, citywalk) [跨商圈]
```

---

## 6. 空间关联网络（Nearby POIs）

### 6.1 设计原则

每个 POI 的 `nearby_pois` 字段维护一个 **步行 5-10 分钟可达** 的地点列表，用于：
- 就近替换
- 路线调整
- 组合推荐

### 6.2 典型空间网络

#### 江边休闲区核心网络
```
滨江公园 (RB004)
  ├── 江风咖啡·露台店 (RB002) - 步行 3 分钟
  ├── 滨江路站 (RB010) - 步行 5 分钟
  ├── 滨江绿道驿站 (RB008) - 步行 2 分钟
  └── 滨江停车场 (RB020) - 步行 8 分钟
```

#### CBD 商圈核心网络
```
银泰中心 (CB001)
  ├── 海底捞·CBD店 (CB003) - 步行 3 分钟
  ├── 中央公园站 (CB011) - 步行 2 分钟
  ├── Wagas·轻食店 (CB005) - 步行 3 分钟
  └── CBD中央公园 (CB002) - 步行 5 分钟
```

#### 商场娱乐区核心网络
```
龙湖天街 (MB001)
  ├── 天街站 (MB014) - 步行 1 分钟
  ├── 绿茶餐厅 (MB003) - 步行 2 分钟
  ├── 天街电影院 (MB009) - 步行 3 分钟
  └── 麦当劳 (MB007) - 步行 2 分钟
```

---

## 7. POI 分类统计

### 7.1 按类别统计

| 类别 | 数量 | 占比 |
|------|------|------|
| restaurant | 25 | 46% |
| hotel | 6 | 11% |
| attraction | 5 | 9% |
| mall | 4 | 7% |
| transport | 6 | 11% |
| entertainment | 5 | 9% |
| resting_area | 3 | 6% |

### 7.2 按价格档位统计

| 价格档位 | 数量 | 占比 |
|----------|------|------|
| low | 18 | 33% |
| medium | 24 | 44% |
| high | 12 | 22% |

### 7.3 按室内外统计

| 类型 | 数量 | 占比 |
|------|------|------|
| indoor | 38 | 70% |
| outdoor | 12 | 22% |
| mixed | 4 | 8% |

---

## 8. Agent 使用指南

### 8.1 加载数据库

```python
import json

# 加载 POI 数据库
with open('poi_database.json', 'r', encoding='utf-8') as f:
    poi_database = json.load(f)

# 构建索引
poi_index = {poi['poi_id']: poi for poi in poi_database}
```

### 8.2 Recovery 推理流程

```python
def recovery_poi(current_poi_id, trigger_event, poi_database):
    """
    Recovery 推理函数
    
    Args:
        current_poi_id: 当前 POI ID
        trigger_event: 触发事件（rainy, traffic, budget_change 等）
        poi_database: POI 数据库
    
    Returns:
        推荐的替代 POI 列表
    """
    current_poi = poi_index[current_poi_id]
    candidates = []
    
    # 获取替换候选
    for candidate_id in current_poi['replacement_candidates']:
        candidate = poi_index[candidate_id]
        
        # 根据事件过滤
        if trigger_event == 'rainy' and candidate['indoor_or_outdoor'] == 'outdoor':
            continue
        
        if trigger_event == 'traffic' and candidate['district'] != current_poi['district']:
            continue
        
        # 检查 recovery_tags
        if is_recovery_tag_match(candidate, trigger_event):
            candidates.append(candidate)
    
    # 按优先级排序
    candidates.sort(key=lambda x: recovery_priority_score(x, trigger_event))
    
    return candidates
```

### 8.3 典型使用场景

#### 场景 1：用户主动 Replan
```
用户输入："不想吃火锅了，换个便宜一点的附近餐厅。"

Agent 处理流程：
1. 解析意图：category=restaurant, price_level=low, action=replace
2. 获取当前 Timeline 中的火锅餐厅 POI
3. 查询 replacement_candidates
4. 过滤 price_level == "low" 的候选
5. 按 nearby_pois 计算距离
6. 返回排序后的推荐列表
```

#### 场景 2：系统被动 Recovery
```
触发事件：检测到下雨

Agent 处理流程：
1. 遍历 Timeline 中未来 2 小时的 POI
2. 筛选 indoor_or_outdoor == "outdoor" 的节点
3. 对每个 outdoor POI 执行 recovery 推理
4. 查询 recovery_tags 包含 "rainy_day_friendly" 的替代
5. 生成 Recovery Plan 并推送给用户确认
```

---

## 9. 数据真实性说明

### 9.1 命名规则

所有 POI 名称采用 **真实品牌 + 分店名** 格式：
- ✅ 川味观·滨江路店
- ✅ 海底捞·CBD店
- ✅ 星巴克臻选
- ✅ 绿茶餐厅
- ✅ Wagas·轻食店

### 9.2 价格合理性

| 类型 | 价格范围 | 示例 |
|------|---------|------|
| 火锅 | 110-130 元 | 海底捞 130 元 |
| 粤菜 | 180-200 元 | 翠园 200 元 |
| 咖啡 | 45-60 元 | 星巴克 50 元 |
| 快餐 | 35-45 元 | 麦当劳 35 元 |
| 商务酒店 | 380-450 元 | 全季 380 元 |
| 豪华酒店 | 680-880 元 | 万豪 880 元 |

### 9.3 营业时间合理性

| 类型 | 营业时间 | 说明 |
|------|---------|------|
| 餐厅 | 10:00-22:00 | 标准餐饮 |
| 快餐 | 07:00-21:00 | 早到晚关 |
| 酒吧 | 18:00-03:00 | 夜间营业 |
| 商场 | 10:00-22:00 | 标准营业 |
| 酒店 | 24h | 全天 |
| 地铁站 | 06:00-23:00 | 运营时间 |

---

## 10. 扩展建议

### 10.1 短期扩展（Phase 1）

- [ ] 增加更多 recovery_tags（如 `pet_friendly`, `wheelchair_accessible`）
- [ ] 增加 POI 之间的距离矩阵
- [ ] 增加营业时间特殊日期（节假日、店休）

### 10.2 中期扩展（Phase 2）

- [ ] 接入真实地图 API（高德/百度）获取实际坐标
- [ ] 增加实时数据（排队时间、空房率、天气影响）
- [ ] 增加用户画像与 POI 偏好匹配

### 10.3 长期扩展（Phase 3）

- [ ] 支持多城市数据库
- [ ] 增加订单关联（可取消、可改签）
- [ ] 增加金融风控字段（退款规则、违约金）

---

## 11. 维护与更新

### 11.1 数据校验

```python
def validate_poi_database(poi_database):
    """校验 POI 数据库完整性"""
    errors = []
    
    for poi in poi_database:
        # 检查必填字段
        required_fields = ['poi_id', 'poi_name', 'district', 'category']
        for field in required_fields:
            if field not in poi:
                errors.append(f"POI {poi.get('poi_id', 'UNKNOWN')} 缺少字段: {field}")
        
        # 检查 replacement_candidates 是否存在
        for candidate_id in poi.get('replacement_candidates', []):
            if candidate_id not in poi_index:
                errors.append(f"POI {poi['poi_id']} 的替换候选 {candidate_id} 不存在")
        
        # 检查 nearby_pois 是否存在
        for nearby_id in poi.get('nearby_pois', []):
            if nearby_id not in poi_index:
                errors.append(f"POI {poi['poi_id']} 的附近 POI {nearby_id} 不存在")
    
    return errors
```

### 11.2 版本管理

建议在文件名中加入版本号：
```
poi_database_v1.json
poi_database_v2.json
```

---

## 12. 联系与反馈

如有问题或建议，请联系项目团队。

---

**文档版本**: v1.0  
**最后更新**: 2026-05-25  
**数据库版本**: poi_database.json (54 POIs)
