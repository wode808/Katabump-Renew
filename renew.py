import os
import time
import subprocess
from seleniumbase import SB

USERNAME = ""
PASSWORD = ""
LOCAL_PROXY = "http://127.0.0.1:8080"

TARGET_SERVER_ID = "233971"
TARGET_URL = f"https://dashboard.katabump.com/servers/edit?id={TARGET_SERVER_ID}"


# ============================================================
# Turnstile 工具函数
# ============================================================

EXPAND_POPUP_JS = """
(function() {
    var turnstileInput = document.querySelector('input[name="cf-turnstile-response"]');
    if (!turnstileInput) return;
    var el = turnstileInput;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var style = window.getComputedStyle(el);
        if (style.overflow === 'hidden' || style.overflowX === 'hidden' || style.overflowY === 'hidden') {
            el.style.overflow = 'visible';
        }
        el.style.minWidth = 'max-content';
    }
    var iframes = document.querySelectorAll('iframe');
    iframes.forEach(function(iframe) {
        if (iframe.src && iframe.src.includes('challenges.cloudflare.com')) {
            iframe.style.width = '300px';
            iframe.style.height = '65px';
            iframe.style.minWidth = '300px';
            iframe.style.visibility = 'visible';
            iframe.style.opacity = '1';
        }
    });
})();
"""


def xdotool_click(x, y):
    """用 xdotool 进行物理鼠标点击"""
    x, y = int(x), int(y)
    try:
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--class", "chrome"],
            capture_output=True, text=True, timeout=3
        )
        wids = [w for w in result.stdout.strip().split('\n') if w]
        if wids:
            subprocess.run(["xdotool", "windowactivate", wids[-1]],
                           timeout=2, stderr=subprocess.DEVNULL)
            time.sleep(0.2)
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], timeout=2, check=True)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, check=True)
        return True
    except Exception as e:
        print(f"    ⚠️ xdotool 点击失败: {e}")
        return False


def get_turnstile_coords(sb):
    """获取 Turnstile iframe 的页面内点击坐标"""
    try:
        return sb.execute_script("""
            (function(){
                var iframes = document.querySelectorAll('iframe');
                for (var i = 0; i < iframes.length; i++) {
                    var src = iframes[i].src || '';
                    if (src.includes('cloudflare') || src.includes('turnstile')) {
                        var rect = iframes[i].getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            return {
                                click_x: Math.round(rect.x + 30),
                                click_y: Math.round(rect.y + rect.height / 2)
                            };
                        }
                    }
                }
                var input = document.querySelector('input[name="cf-turnstile-response"]');
                if (input) {
                    var container = input.parentElement;
                    for (var j = 0; j < 5; j++) {
                        if (!container) break;
                        var rect = container.getBoundingClientRect();
                        if (rect.width > 100 && rect.height > 30) {
                            return {
                                click_x: Math.round(rect.x + 30),
                                click_y: Math.round(rect.y + rect.height / 2)
                            };
                        }
                        container = container.parentElement;
                    }
                }
                return null;
            })()
        """)
    except Exception:
        return None


def get_window_offset(sb):
    """获取窗口屏幕偏移和 toolbar 高度"""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--class", "chrome"],
            capture_output=True, text=True, timeout=3
        )
        wids = [w for w in result.stdout.strip().split('\n') if w]
        if wids:
            geo = subprocess.run(
                ["xdotool", "getwindowgeometry", "--shell", wids[-1]],
                capture_output=True, text=True, timeout=3
            ).stdout
            geo_dict = {}
            for line in geo.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    geo_dict[k.strip()] = int(v.strip())
            win_x = geo_dict.get('X', 0)
            win_y = geo_dict.get('Y', 0)
            info = sb.execute_script(
                "(function(){ return { outer: window.outerHeight, inner: window.innerHeight }; })()"
            )
            toolbar = info['outer'] - info['inner']
            if not (30 <= toolbar <= 200):
                toolbar = 87
            return win_x, win_y, toolbar
    except Exception:
        pass
    # 回退：JS 获取
    try:
        info = sb.execute_script("""
            (function(){
                return {
                    screenX: window.screenX || 0,
                    screenY: window.screenY || 0,
                    outer: window.outerHeight,
                    inner: window.innerHeight
                };
            })()
        """)
        toolbar = info['outer'] - info['inner']
        if not (30 <= toolbar <= 200):
            toolbar = 87
        return info['screenX'], info['screenY'], toolbar
    except Exception:
        return 0, 0, 87


def check_token(sb) -> bool:
    try:
        return sb.execute_script("""
            (function(){
                var input = document.querySelector('input[name="cf-turnstile-response"]');
                return input && input.value && input.value.length > 20;
            })()
        """)
    except Exception:
        return False


def turnstile_exists(sb) -> bool:
    try:
        return sb.execute_script(
            "(function(){ return document.querySelector('input[name=\"cf-turnstile-response\"]') !== null; })()"
        )
    except Exception:
        return False


def solve_turnstile(sb) -> bool:
    """修复样式，物理点击 Turnstile，等待 token（单次，15秒超时）"""
    # 修复 iframe 样式
    for _ in range(3):
        sb.execute_script(EXPAND_POPUP_JS)
        time.sleep(0.5)

    # 已通过则跳过
    if check_token(sb):
        print("✅ Turnstile 已通过（无需点击）")
        return True

    # 获取坐标并点击
    coords = get_turnstile_coords(sb)
    if not coords:
        print("❌ 无法获取 Turnstile 坐标")
        return False

    win_x, win_y, toolbar = get_window_offset(sb)
    abs_x = coords['click_x'] + win_x
    abs_y = coords['click_y'] + win_y + toolbar
    print(f"    🖱️ 点击 Turnstile: ({abs_x}, {abs_y})")
    xdotool_click(abs_x, abs_y)

    # 等待 token（最多 15 秒）
    for _ in range(30):
        time.sleep(0.5)
        if check_token(sb):
            print("✅ Turnstile 验证通过")
            return True

    print("❌ Turnstile 验证超时")
    sb.save_screenshot("turnstile_fail.png")
    return False


# ============================================================
# 主流程
# ============================================================

def run_script():
    print("🔧 [Katabump-Renew] 启动浏览器")

    with SB(uc=True, test=True, proxy=LOCAL_PROXY) as sb:
        print("🚀 浏览器已启动")

        # ── IP 验证 ──────────────────────────────────────────
        print("[-] 正在验证代理 IP...")
        try:
            sb.open("https://api.ipify.org/?format=json")
            print(f"✅ 当前出口 IP: {sb.get_text('body')}")
        except Exception:
            print("⚠️ IP 验证超时，跳过")

        # ── 登录 ─────────────────────────────────────────────
        print("[-] 访问登录页...")
        sb.uc_open_with_reconnect("https://dashboard.katabump.com/auth/login", reconnect_time=4)
        time.sleep(3)

        print("[-] 输入账号密码...")
        try:
            sb.wait_for_element_visible('input[name="email"]', timeout=20)
            sb.type('input[name="email"]', USERNAME)
            sb.type('input[name="password"]', PASSWORD)
        except Exception:
            print("❌ 无法加载登录框")
            sb.save_screenshot("login_fail.png")
            return

        # 等待 Turnstile 加载（最多 5 秒）
        for _ in range(10):
            time.sleep(0.5)
            if turnstile_exists(sb):
                break

        if turnstile_exists(sb):
            print("[-] 检测到 Turnstile，开始解决...")
            if not solve_turnstile(sb):
                sb.save_screenshot("login_turnstile_fail.png")
                return
        else:
            print("[-] 无 Turnstile，直接提交...")

        try:
            sb.click('button[type="submit"]')
        except Exception:
            print("❌ 无法点击登录按钮")
            sb.save_screenshot("login_submit_fail.png")
            return

        print("[-] 等待登录跳转...")
        for _ in range(80):
            try:
                if "/dashboard" in sb.get_current_url():
                    print("✅ 登录成功！")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            print("❌ 登录超时")
            sb.save_screenshot("login_timeout.png")
            return

        # ── 跳转服务器页面 ────────────────────────────────────
        print(f"[-] 跳转服务器页面: {TARGET_URL}")
        sb.execute_script(f"window.location.href = '{TARGET_URL}';")
        time.sleep(4)

        if "auth/login" in sb.get_current_url():
            print("❌ 被踢回登录页")
            sb.save_screenshot("server_page.png")
            return

        sb.save_screenshot("server_page.png")

        # ── 寻找 Renew 按钮 ───────────────────────────────────
        print("[-] 寻找 Renew 按钮...")
        renew_btn = None
        for sel in [
            'button[data-bs-target="#renew-modal"]',
            'button[data-target="#renew-modal"]',
            'a[data-bs-target="#renew-modal"]',
            '//button[contains(translate(text(),"renew","RENEW"),"RENEW")]',
        ]:
            try:
                if sb.is_element_visible(sel):
                    renew_btn = sel
                    print(f"✅ 找到 Renew 按钮: {sel}")
                    break
            except Exception:
                continue

        if not renew_btn:
            print("❌ 找不到 Renew 按钮")
            sb.save_screenshot("no_renew_btn.png")
            return

        try:
            sb.click(renew_btn)
            print("✅ 已点击 Renew 按钮，等待弹窗...")
            time.sleep(2)

            # ── 等待 Turnstile 出现 ───────────────────────────
            print("[-] 等待 Turnstile...")
            for _ in range(20):
                if turnstile_exists(sb):
                    print("✅ 检测到 Turnstile")
                    break
                time.sleep(1)
            else:
                print("❌ Turnstile 未出现")
                sb.save_screenshot("no_turnstile.png")
                return

            # ── 解决 Turnstile ────────────────────────────────
            if not solve_turnstile(sb):
                return

            # ── 提交 Confirm ──────────────────────────────────
            print("🎯 提交续期...")
            confirm_btn = '#renew-modal button[type="submit"]'
            if not sb.is_element_visible(confirm_btn):
                print("❌ 找不到 Confirm 按钮")
                sb.save_screenshot("no_confirm_btn.png")
                return

            sb.click(confirm_btn)
            print("[-] 已点击 Confirm...")
            time.sleep(5)

            if sb.is_element_visible('.alert-danger'):
                alert_text = sb.get_text('.alert-danger')
                if "can't renew" in alert_text or "in 3 day" in alert_text:
                    print("✅ 未到期，无需续期")
                    sb.save_screenshot("renew_too_early.png")
                else:
                    print(f"⚠️ 错误提示: {alert_text}")
                    sb.save_screenshot("renew_error.png")
            elif sb.is_element_visible('.alert-success'):
                print("🎉🎉🎉 续期成功！")
                sb.save_screenshot("renew_success.png")
            else:
                print("ℹ️ 提交完成（无明确状态）")
                sb.save_screenshot("unknown_result.png")

        except Exception as e:
            print(f"❌ 操作异常: {e}")
            sb.save_screenshot("error_renew.png")


if __name__ == "__main__":
    run_script()
