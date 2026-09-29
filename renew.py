import os
import time
import subprocess
from seleniumbase import SB

USERNAME = ""
PASSWORD = ""
LOCAL_PROXY = "http://127.0.0.1:8080"

TARGET_SERVER_ID = "387768"
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

        # ── 寻找 Renew 按钮 ────────────────────────────────────
        print("[-] 寻找 Renew 按钮...")

        try:
            print(f"🌐 当前页面 URL: {sb.get_current_url()}")
            print(f"📄 当前页面标题: {sb.get_title()}")
        except Exception:
            pass

        renew_btn = None

        # 不依赖固定的 #renew-modal，也不限制必须是 button/a。
        # 直接从当前 DOM 中寻找“可见 + 文本/属性包含 Renew”的元素。
        try:
            renew_info = sb.execute_script("""
                const els = Array.from(document.querySelectorAll('*'));

                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 &&
                           r.height > 0 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                function textOf(el) {
                    return (
                        el.innerText ||
                        el.textContent ||
                        el.value ||
                        el.getAttribute('aria-label') ||
                        el.getAttribute('title') ||
                        ''
                    ).trim();
                }

                const candidates = els.filter(el => {
                    if (!visible(el)) return false;
                    const t = textOf(el).toLowerCase();
                    return t.includes('renew');
                });

                // 优先真正可点击的元素，并尽量选择最小的元素，
                // 避免选到包住整个卡片的父级 div。
                const clickable = candidates.filter(el => {
                    const tag = el.tagName.toLowerCase();
                    return ['button', 'a', 'input'].includes(tag) ||
                           typeof el.onclick === 'function' ||
                           el.getAttribute('role') === 'button' ||
                           getComputedStyle(el).cursor === 'pointer';
                });

                const list = (clickable.length ? clickable : candidates)
                    .map(el => ({
                        tag: el.tagName,
                        text: textOf(el),
                        id: el.id || '',
                        cls: typeof el.className === 'string' ? el.className : '',
                        type: el.getAttribute('type') || '',
                        value: el.value || '',
                        href: el.getAttribute('href') || '',
                        target: el.getAttribute('data-bs-target') ||
                                el.getAttribute('data-target') || '',
                        outerHTML: el.outerHTML.substring(0, 1500)
                    }));

                return list;
            """)

            print("========== Renew 候选元素 ==========")
            for item in renew_info:
                print(item)
            print("====================================")

            if renew_info:
                print("✅ DOM 中确认存在 Renew 元素")

                # 不用 Selenium selector 猜元素，直接由 JS 找到最合适的可点击 Renew。
                clicked = sb.execute_script("""
                    const els = Array.from(document.querySelectorAll('*'));

                    function visible(el) {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 &&
                               r.height > 0 &&
                               s.display !== 'none' &&
                               s.visibility !== 'hidden' &&
                               s.opacity !== '0';
                    }

                    function textOf(el) {
                        return (
                            el.innerText ||
                            el.textContent ||
                            el.value ||
                            el.getAttribute('aria-label') ||
                            el.getAttribute('title') ||
                            ''
                        ).trim();
                    }

                    const candidates = els.filter(el => {
                        if (!visible(el)) return false;
                        const t = textOf(el).toLowerCase();
                        if (!t.includes('renew')) return false;

                        const tag = el.tagName.toLowerCase();
                        return ['button', 'a', 'input'].includes(tag) ||
                               el.getAttribute('role') === 'button' ||
                               getComputedStyle(el).cursor === 'pointer' ||
                               typeof el.onclick === 'function';
                    });

                    if (!candidates.length) return false;

                    // 优先最底层/最小的可点击元素
                    candidates.sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.width * ar.height) - (br.width * br.height);
                    });

                    const el = candidates[0];
                    el.scrollIntoView({block: 'center', inline: 'center'});

                    const r = el.getBoundingClientRect();

                    // 保存信息给日志
                    window.__renew_clicked_info = {
                        tag: el.tagName,
                        text: textOf(el),
                        id: el.id || '',
                        target: el.getAttribute('data-bs-target') ||
                                el.getAttribute('data-target') || '',
                        outerHTML: el.outerHTML.substring(0, 1500)
                    };

                    // 先使用原生 click，触发 Bootstrap/前端事件。
                    el.click();
                    return true;
                """)

                if clicked:
                    info = sb.execute_script("return window.__renew_clicked_info || null;")
                    print(f"✅ 已通过 DOM 原生 click 点击 Renew: {info}")
                    renew_btn = "__JS_CLICKED__"
                else:
                    print("❌ 找到了 Renew 文本，但没有找到可点击元素")

        except Exception as e:
            print(f"⚠️ Renew DOM 扫描异常: {e}")

        if not renew_btn:
            print("❌ 找不到 Renew 按钮")
            print("💡 已保存当前页面截图和 DOM 信息")
            sb.save_screenshot("no_renew_btn.png")

            try:
                with open("page_buttons_dump.txt", "w", encoding="utf-8") as f:
                    data = sb.execute_script("""
                        return Array.from(document.querySelectorAll(
                            'button, a, input, [role="button"]'
                        )).map(el => ({
                            tag: el.tagName,
                            text: (el.innerText || el.textContent || el.value || '').trim(),
                            id: el.id || '',
                            cls: typeof el.className === 'string' ? el.className : '',
                            type: el.getAttribute('type') || '',
                            target: el.getAttribute('data-bs-target') ||
                                    el.getAttribute('data-target') || '',
                            outerHTML: el.outerHTML.substring(0, 2000)
                        }));
                    """)
                    for item in data:
                        f.write(str(item) + "\\n")
                print("📄 已生成 page_buttons_dump.txt")
            except Exception as e:
                print(f"⚠️ DOM 导出失败: {e}")

            return

        try:
            # 如果已经通过 JS 点击 Renew，这里不重复点击。
            # ── 等待 Renew 弹窗/Turnstile 出现 ─────────────────
            print("[-] 等待 Renew 弹窗和 Turnstile...")

            for _ in range(20):
                if turnstile_exists(sb):
                    print("✅ 检测到 Renew 弹窗中的 Turnstile")
                    break
                time.sleep(1)
            else:
                print("❌ Turnstile 未出现")
                print("🔎 输出当前可见 dialog/modal...")

                try:
                    dialogs = sb.execute_script("""
                        return Array.from(document.querySelectorAll(
                            '[role="dialog"], .modal, [id*="renew" i]'
                        )).map(el => ({
                            tag: el.tagName,
                            id: el.id || '',
                            cls: typeof el.className === 'string' ? el.className : '',
                            visible: (() => {
                                const r = el.getBoundingClientRect();
                                const s = getComputedStyle(el);
                                return r.width > 0 && r.height > 0 &&
                                       s.display !== 'none' &&
                                       s.visibility !== 'hidden';
                            })(),
                            text: (el.innerText || el.textContent || '').trim().substring(0, 1000),
                            html: el.outerHTML.substring(0, 3000)
                        }));
                    """)
                    for d in dialogs:
                        print(d)
                except Exception as e:
                    print(f"⚠️ Modal 扫描失败: {e}")

                sb.save_screenshot("no_turnstile.png")
                return

            # ── 解决 Turnstile ────────────────────────────────
            if not solve_turnstile(sb):
                return

            # ── 提交 Confirm ──────────────────────────────────
            print("🎯 查找续期确认按钮...")

            confirm_clicked = sb.execute_script("""
                const dialogs = Array.from(document.querySelectorAll(
                    '[role="dialog"], .modal'
                )).filter(el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden';
                });

                const root = dialogs.length ? dialogs[dialogs.length - 1] : document;

                const els = Array.from(root.querySelectorAll(
                    'button, input[type="submit"], input[type="button"], a, [role="button"]'
                ));

                function txt(el) {
                    return (
                        el.innerText ||
                        el.textContent ||
                        el.value ||
                        el.getAttribute('aria-label') ||
                        el.getAttribute('title') ||
                        ''
                    ).trim().toLowerCase();
                }

                const candidates = els.filter(el => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    if (!(r.width > 0 && r.height > 0) ||
                        s.display === 'none' ||
                        s.visibility === 'hidden') return false;

                    const t = txt(el);
                    return t.includes('confirm') ||
                           t.includes('renew') ||
                           t.includes('延長') ||
                           t.includes('期限');
                });

                if (!candidates.length) return false;

                candidates[0].scrollIntoView({block: 'center'});
                candidates[0].click();

                window.__confirm_clicked_info = {
                    tag: candidates[0].tagName,
                    text: txt(candidates[0]),
                    outerHTML: candidates[0].outerHTML.substring(0, 1500)
                };

                return true;
            """)

            if not confirm_clicked:
                print("❌ 找不到 Confirm/Renew 确认按钮")
                sb.save_screenshot("no_confirm_btn.png")
                return

            print(
                f"✅ 已点击确认按钮: "
                f"{sb.execute_script('return window.__confirm_clicked_info || null;')}"
            )
            print("[-] 已点击 Confirm...")
            time.sleep(5)

            if sb.is_element_visible('.alert-danger'):
                alert_text = sb.get_text('.alert-danger')
                if "can't renew" in alert_text.lower() or "in 3 day" in alert_text.lower():
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
