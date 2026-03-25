import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
  const password = process.env.APP_PASSWORD

  // 如果冇設定密碼，直接放行
  if (!password) {
    return NextResponse.next()
  }

  // 檢查 cookie
  const authCookie = request.cookies.get('auth_password')

  if (authCookie?.value === password) {
    return NextResponse.next()
  }

  // 檢查 header (POST 登入表單)
  if (request.method === 'POST') {
    const formData = await request.formData()
    const submittedPassword = formData.get('password')

    if (submittedPassword === password) {
      const response = NextResponse.redirect(new URL('/', request.url))
      response.cookies.set('auth_password', password, {
        httpOnly: true,
        secure: false, // VPS 用 HTTP
        maxAge: 60 * 60 * 24 * 7, // 7 days
        path: '/',
        sameSite: 'lax',
      })
      return response
    }
  }

  // 返回登入頁面
  return new NextResponse(
    `<!DOCTYPE html>
<html lang="zh-HK">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>登入 - Position Calculator</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #141414;
      color: #e5e5e5;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .login-box {
      background: #1a1a1a;
      padding: 40px;
      border-radius: 12px;
      border: 1px solid #333;
      width: 100%;
      max-width: 360px;
    }
    h1 { font-size: 24px; margin-bottom: 8px; color: #fff; }
    p { color: #888; margin-bottom: 24px; font-size: 14px; }
    input {
      width: 100%;
      padding: 12px 16px;
      background: #2a2a2a;
      border: 1px solid #444;
      border-radius: 8px;
      color: #fff;
      font-size: 16px;
      margin-bottom: 16px;
    }
    input:focus { outline: none; border-color: #3b82f6; }
    button {
      width: 100%;
      padding: 12px;
      background: #3b82f6;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-size: 16px;
      cursor: pointer;
      font-weight: 500;
    }
    button:hover { background: #2563eb; }
    .error { color: #ef4444; font-size: 14px; margin-bottom: 16px; }
  </style>
</head>
<body>
  <div class="login-box">
    <h1>🔐 Position Calculator</h1>
    <p>請輸入密碼以繼續</p>
    <form method="POST">
      <input type="password" name="password" placeholder="密碼" required autofocus />
      <button type="submit">登入</button>
    </form>
  </div>
</body>
</html>`,
    {
      status: 401,
      headers: { 'Content-Type': 'text/html' },
    }
  )
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}
