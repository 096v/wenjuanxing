from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random
import time
import threading
import pyautogui
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from proxy_pool import ProxyPool, quick_pool

# 全局锁：pyautogui 不能多线程并发操作鼠标，所有滑块验证必须排队
PYAUTOGUI_LOCK = threading.Lock()


def get_element_screen_pos(driver, element):
    """获取元素相对于屏幕的实际坐标"""
    location = element.location
    size = element.size
    browser_pos = driver.get_window_position()
    
    # 计算元素中心点的屏幕坐标
    x = location['x'] + browser_pos['x'] + size['width'] // 2
    y = location['y'] + browser_pos['y'] + size['height'] // 2 + 80
    return x, y

def human_drag_trajectory(start_x, start_y, end_x, end_y, duration=None):
    """模拟人类拖拽轨迹：变速+随机抖动"""
    if duration is None:
        duration = random.uniform(1.0, 2.0)
    
    steps = int(duration * 50)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.15))
    
    for i in range(1, steps + 1):
        progress = i / steps
        ease_progress = 1 - (1 - progress) ** 3
        target_x = start_x + (end_x - start_x) * ease_progress
        target_y = start_y + (end_y - start_y) * ease_progress
        jitter_y = random.gauss(0, 1.5)
        current_x = target_x
        current_y = target_y + jitter_y
        pyautogui.moveTo(current_x, current_y)
        time.sleep(duration / steps)
    pyautogui.moveTo(end_x - random.randint(1, 3), end_y)
    time.sleep(random.uniform(0.05, 0.1))
    pyautogui.moveTo(end_x, end_y)
    time.sleep(random.uniform(0.05, 0.1))
    
    pyautogui.mouseUp(button='left')

def huakuai_improved(driver):
    """改进版滑块验证：动态坐标+人类轨迹"""
    try:
        slider_btn = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#rectBottom'))
        )
        start_x, start_y = get_element_screen_pos(driver, slider_btn)
        slider_btn.click()
        time.sleep(random.uniform(0.3, 0.6))
        drag_distance = random.randint(280, 380)
        end_x = start_x + drag_distance
        end_y = start_y

        with PYAUTOGUI_LOCK:
            human_drag_trajectory(start_x, start_y, end_x, end_y)

        time.sleep(random.uniform(1.0, 2.0))
        print("滑块验证完成")

    except Exception as e:
        print(f"滑块验证出错: {e}")
        huakuai_fallback()

def huakuai_fallback():
    """降级方案：当无法定位元素时使用固定坐标"""
    with PYAUTOGUI_LOCK:
        pyautogui.moveTo(random.randint(494, 496), 791, 0.2)
        time.sleep(1)
        pyautogui.dragTo(random.randint(888, 890), 791, 1)
        time.sleep(1)
        pyautogui.click(random.randint(652, 667), random.randint(793, 795))
        time.sleep(1)
        pyautogui.moveTo(random.randint(494, 496), 791, 0.2)
        time.sleep(1)
        pyautogui.dragTo(random.randint(888, 890), 791, 1)


def handle_dropdown(driver, selector):
    """优化版下拉框处理：增强型 JS 注入 + 稳健降级"""
    try:
        # 1. 显式等待题目容器加载
        q_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

        # 2. 平滑滚动到视野中心，并等待让前端组件渲染完毕
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", q_box)
        time.sleep(random.uniform(0.5, 0.8))

        # 从 #div1 提取出数字 1
        q_num = selector.replace('#div', '')

        # 3. 增强版 JS 注入：同时尝试多种可能的 select 标签定位方式
        js_code = f"""
        // 尝试匹配 q1, select_q1 或者是 div1 下的 select 元素
        var selectEl = document.getElementById('q{q_num}') ||
                       document.getElementById('select_q{q_num}') ||
                       document.querySelector('{selector} select');

        if (selectEl) {{
            var options = selectEl.options;
            var validIndices = [];
            for (var i = 0; i < options.length; i++) {{
                var text = options[i].text;
                var val = options[i].value;
                // 过滤掉提示语、空值或带有"请选择"的选项
                if (val && val !== "0" && text.indexOf("请选择") === -1 && text.trim() !== "") {{
                    validIndices.push(i);
                }}
            }}
            if (validIndices.length > 0) {{
                var randomIndex = validIndices[Math.floor(Math.random() * validIndices.length)];
                selectEl.selectedIndex = randomIndex;

                // 触发 change 事件通知前端框架更新数据
                selectEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
                if (window.jQuery && jQuery(selectEl).data('select2')) {{
                    jQuery(selectEl).trigger('change');
                }}
                return options[randomIndex].text;
            }}
        }}
        return null;
        """
        result = driver.execute_script(js_code)

        if result:
            print(f" {selector} 通过 JS 强选成功: 【{result}】")
            return

        # 4. 如果 JS 注入彻底失败，使用 Selenium 原生 DOM 点击保底（比 PyAutoGUI 按键更安全）
        print(f"⚠️ {selector} JS 注入未能选中，切换到原生 DOM 点击保底")

        # 寻找问卷星下拉框的视觉触发框
        trigger = q_box.find_element(By.CSS_SELECTOR, ".select2-selection, .ui-select, [class*='select']")
        driver.execute_script("arguments[0].click();", trigger)
        time.sleep(0.5)

        # 寻找弹出的下拉框选项列表
        options = driver.find_elements(By.CSS_SELECTOR, ".select2-results__option, dd, li")
        valid_options = [o for o in options if o.is_displayed() and "请选择" not in o.text and o.text.strip()]

        if valid_options:
            target_opt = random.choice(valid_options)
            driver.execute_script("arguments[0].click();", target_opt)
            print(f" {selector} 通过 DOM 保底点击成功: 【{target_opt.text.strip()}】")
        else:
            raise NoSuchElementException("未找到可点击的下拉候选菜单项")

    except Exception as e:
        print(f" ❌ {selector} 下拉框所有方法均失效，请检查页面结构: {e}")


def handle_matrix(driver, selector):
    """处理矩阵题"""
    try:
        matrix_box = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", matrix_box)
        rows = matrix_box.find_elements(By.CSS_SELECTOR, "tr[id^='drv'], tr[sectype='1']")
        for row in rows:
            btns = row.find_elements(By.CSS_SELECTOR, "a.jqradio, .ui-radio, td")
            choices = btns[1:] if len(btns) > 1 else btns
            if choices:
                target = random.choice(choices)
                driver.execute_script("arguments[0].click();", target)
                time.sleep(random.uniform(0.2, 0.4))
        print(f" {selector} 矩阵题处理完成")
    except Exception as e:
        print(f" {selector} 矩阵题处理失败: {e}")


def handle_sort_question(driver, selector):
    """排序题：打乱顺序全选"""
    try:
        q_box = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", q_box)
        time.sleep(0.5)

        items = q_box.find_elements(By.CSS_SELECTOR, "li, .ui-checkbox, .jqcheck")
        
        if items:
            indices = list(range(len(items)))
            random.shuffle(indices) 
            
            print(f"开始对 {selector} 进行排序，共 {len(items)} 项")
            for idx in indices:

                driver.execute_script("arguments[0].click();", items[idx])
                time.sleep(random.uniform(0.4, 0.7))
            print(f" {selector} 排序题（全选乱序）完成")
    except Exception as e:
        print(f" {selector} 排序题处理失败: {e}")


def handle_question(driver, selector, answer_type='radio', valid_ans_count=1):
    """处理普通单选多选"""
    try:
        q_box = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", q_box)

        css = ".ui-radio, .ui-checkbox, .jqradio, .jqcheck, li"
        ans = q_box.find_elements(By.CSS_SELECTOR, css)
        ans = [a for a in ans if a.is_displayed() and "其他" not in a.text and a.text.strip()]
        
        if ans:
            num = 1 if answer_type == 'radio' else random.randint(1, min(valid_ans_count, len(ans)))
            for target in random.sample(ans, num):
                driver.execute_script("arguments[0].click();", target)
                time.sleep(0.3)
            print(f" {selector} 处理成功")
    except Exception as e:
        print(f" {selector} 跳过: {e}")


def scroll_to_element(driver, element):
    driver.execute_script("arguments[0].scrollIntoView();", element)


def tiankong(driver, num):
    answers_pool = [
        "无", "好", "good", "不错", "还可以", "满意", "挺好",
        "暂无", "没有", "不清楚", "一般般", "还行吧", "挺好的",
        "非常满意", "比较满意", "一般", "有待改进", "希望更好",
        "谢谢", "感谢", "辛苦了", "非常好", "很棒", "优秀",
        "A", "B", "C", "D", "E", "F", "G",
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
        "是", "否", "对", "错", "有", "没有"
    ]
    try:
        input_element = driver.find_element(By.CSS_SELECTOR, f'#q{num}')
        if random.random() > 0.1:
            answer = random.choice(answers_pool)
            input_element.send_keys(answer)
            time.sleep(random.uniform(0.3, 0.8))
    except NoSuchElementException:
        print(f"未找到第 {num} 题的填空题输入框。")


def renzheng(driver):
    wait = WebDriverWait(driver, 10)
    try:
        bth = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                                                         '#layui-layer1 > div.layui-layer-btn.layui-layer-btn- > a.layui-layer-btn0')))
        bth.click()
        time.sleep(random.uniform(0.8, 1.5))
        rectBottom = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '#rectBottom')))
        rectBottom.click()
        time.sleep(random.uniform(1.5, 2.5))
        # 使用改进版滑块验证
        huakuai_improved(driver)
    except TimeoutException:
        print("本次未出现认证界面，继续进行后续操作")


def gundong(driver, distance):
    js = "var q=document.documentElement.scrollTop=" + str(distance)
    driver.execute_script(js)
    time.sleep(1)


def load_config(config_path="survey_config.yaml"):
    """加载 YAML 配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def execute_survey_from_yaml(driver, config_data):
    """根据 YAML 配置数据自动循环答题"""
    questions = config_data.get('questions', [])

    for q in questions:
        q_id = q['id']
        q_type = q['type']
        q_desc = q.get('desc', q_id)
        selector = f"#{q_id}"

        print(f"正在处理 -> {q_desc} [类型: {q_type}]")

        # 根据 YAML 中定义的 type，分发给不同的处理函数
        if q_type == 'dropdown':
            handle_dropdown(driver, selector)

        elif q_type == 'radio':
            handle_question(driver, selector, answer_type='radio')

        elif q_type == 'checkbox':
            max_c = q.get('max_choices', 1)
            handle_question(driver, selector, answer_type='checkbox', valid_ans_count=max_c)

        elif q_type == 'matrix':
            handle_matrix(driver, selector)

        elif q_type == 'sort':
            handle_sort_question(driver, selector)

        elif q_type == 'text':
            num = q['input_id'].replace('q', '')
            tiankong(driver, num)

        else:
            print(f"⚠️ 未知的题目类型: {q_type}，跳过该题。")

        # 题目之间的随机间隔（符合人类操作习惯）
        time.sleep(random.uniform(0.5, 1.2))


def _build_edge_driver(proxy=None):
    """创建配置好的 Edge 浏览器实例

    Args:
        proxy: 代理字符串，如 "66.29.154.103:3128"，None 则直连

    Returns:
        webdriver.Edge
    """
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    option = EdgeOptions()
    option.add_experimental_option('excludeSwitches', ['enable-automation'])
    option.add_experimental_option('useAutomationExtension', False)
    option.add_argument("--disable-blink-features=AutomationControlled")
    option.add_argument('--disable-extensions')
    option.add_argument('--no-sandbox')
    option.add_argument('--disable-dev-shm-usage')
    option.add_argument("--disable-infobars")
    option.add_argument(f'user-agent={random.choice(user_agents)}')

    # ========== 代理配置 ==========
    if proxy:
        option.add_argument(f'--proxy-server=http://{proxy}')
        print(f"    使用代理: {proxy}")

    driver = webdriver.Edge(options=option)

    # 隐藏webdriver属性
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',
                           {'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'})

    # 随机窗口大小
    width = random.randint(1000, 1400)
    height = random.randint(800, 1000)
    driver.set_window_size(width, height)

    return driver


def run_single_task(times, config_path="survey_config.yaml", proxy=None, task_id=1):
    """单个任务：完成 times 次问卷提交

    Args:
        times: 该任务提交次数
        config_path: YAML 配置文件路径
        proxy: 代理字符串，如 "66.29.154.103:3128"（None 则直连）
        task_id: 任务编号（多线程时用于日志区分）
    """
    prefix = f"[任务-{task_id}]"

    config = load_config(config_path)
    settings = config.get('settings', {})
    url_survey = settings.get('url', 'https://v.wjx.cn/vm/PyKgkYl.aspx#')
    submit_selector = settings.get('submit_selector', '#ctlNext')
    success_keyword = settings.get('success_keyword', '您的答卷已经提交')

    print(f"{prefix} 启动: 共 {times} 次, 代理={proxy or '直连'}")

    for i in range(times):
        print(f"{prefix} 第 {i+1}/{times} 次开始...")

        driver = _build_edge_driver(proxy=proxy)

        # 随机延迟后再开始
        time.sleep(random.uniform(2, 5))

        driver.get(url_survey)

        # 等待页面完全加载
        page_loaded = False
        for selector in ['#div1', '.ui-controlgroup', '[id^="q"]', '.field-ui']:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"{prefix} 页面加载完成（检测到 {selector}）")
                page_loaded = True
                break
            except TimeoutException:
                continue

        if not page_loaded:
            print(f"{prefix} 警告：未检测到标准题目元素，尝试继续执行...")

        time.sleep(3)

        # 快速调试（仅在首次或出错时详细输出）
        try:
            radios = driver.find_elements(By.CSS_SELECTOR, '.ui-radio')
            checkboxes = driver.find_elements(By.CSS_SELECTOR, '.ui-checkbox')
            print(f"{prefix} 检测到单选:{len(radios)} 多选:{len(checkboxes)}")
        except Exception:
            pass

        execute_survey_from_yaml(driver, config)

        try:
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, submit_selector)))
            driver.find_element(By.CSS_SELECTOR, submit_selector).click()
        except TimeoutException:
            print(f"{prefix} 未找到下一步按钮，可能页面加载异常。")

        # 滑块验证（pyautogui 已内部加锁，多线程安全）
        renzheng(driver)

        try:
            success_xpath = f'//div[@id="divdsc" and contains(text(), "{success_keyword}")]'
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, success_xpath))
            )
            print(f'{prefix} ✅ 问卷提交成功！')
        except TimeoutException:
            print(f'{prefix} ⚠️ 未检测到提交成功提示')

        print(f'{prefix} 已完成 {i+1}/{times} 次')
        driver.quit()

        # 每次提交后随机间隔
        if i < times - 1:
            wait_time = random.randint(10, 30)
            print(f'{prefix} 等待 {wait_time}s ...')
            time.sleep(wait_time)

    print(f"{prefix} 🏁 全部完成！共提交 {times} 次")


def run_concurrent(total_times, config_path="survey_config.yaml", thread_count=3,
                   fetch_proxy="127.0.0.1:7897", proxy_count=5):
    """多线程并发执行问卷任务

    Args:
        total_times: 总提交次数（会均匀分配到各线程）
        config_path: YAML 配置文件路径
        thread_count: 并发线程数
        fetch_proxy: 抓取代理时用的代理（翻墙用），None 则不抓取在线代理
        proxy_count: 目标可用代理数
    """
    print(f"\n{'='*60}")
    print(f"🚀 多线程模式启动")
    print(f"   总次数: {total_times} | 线程数: {thread_count} | 代理目标: {proxy_count}")
    print(f"{'='*60}\n")

    # 1. 获取代理池
    proxy_list = []
    if fetch_proxy:
        try:
            pool = quick_pool(fetch_proxy=fetch_proxy, target_count=proxy_count)
            proxy_list = pool.get_unique_proxies(thread_count)
            print(f"[主线程] 获取到 {len(proxy_list)} 个代理\n")
        except Exception as e:
            print(f"[主线程] 代理池初始化失败: {e}，将使用直连模式\n")
    else:
        print("[主线程] 未配置代理抓取通道，使用直连模式\n")

    # 2. 分配任务：每个线程提交次数
    per_thread = [total_times // thread_count] * thread_count
    for i in range(total_times % thread_count):
        per_thread[i] += 1

    print(f"[主线程] 任务分配: {per_thread}\n")

    # 3. 并发执行
    results = []
    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = {}
        for tid in range(thread_count):
            proxy = proxy_list[tid] if tid < len(proxy_list) else None
            futures[executor.submit(
                run_single_task,
                times=per_thread[tid],
                config_path=config_path,
                proxy=proxy,
                task_id=tid + 1
            )] = tid + 1

        for future in as_completed(futures):
            tid = futures[future]
            try:
                future.result()
                results.append((tid, True))
            except Exception as e:
                print(f"[任务-{tid}] ❌ 异常: {e}")
                results.append((tid, False))

    # 4. 汇总
    success = sum(1 for _, ok in results if ok)
    print(f"\n{'='*60}")
    print(f"🏁 全部任务完成！成功 {success}/{len(results)} 个线程")
    print(f"{'='*60}\n")


# 保留旧函数名作为兼容别名
def zonghe(times, config_path="survey_config.yaml"):
    """兼容旧接口：单线程顺序执行，不使用代理"""
    run_single_task(times, config_path=config_path, proxy=None, task_id=1)


if __name__ == "__main__":
    import sys

    # 默认：多线程模式，3 线程，共提交 10 次
    # 用法：
    #   python main.py                      → 多线程模式（3线程，10次）
    #   python main.py single               → 单线程模式（1次，兼容旧版）
    #   python main.py single 5             → 单线程模式（5次）
    #   python main.py multi 20 5           → 多线程模式（5线程，总20次）

    if len(sys.argv) > 1 and sys.argv[1] == "single":
        times = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        zonghe(times, "survey_config.yaml")
    else:
        total = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
        threads = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 3
        run_concurrent(
            total_times=total,
            config_path="survey_config.yaml",
            thread_count=threads,
            fetch_proxy="127.0.0.1:7897",  # 本地代理：用于翻墙抓取在线代理列表
            proxy_count=5,                  # 目标获取 5 个可用代理
        )