declare module 'futu-api/proto.js' {
  const protoRoot: any
  export default protoRoot
}

declare module 'futu-api' {
  interface FutuOptions {
    ip: string
    port: number
    userID?: number
    pwdMd5?: string
  }

  interface FutuInstance {
    start(ip: string, port: number, isSSL: boolean, certPath: string | null): void
    close(): void
    onlogin: (ret: number, msg: string) => void
    on(event: string, callback: (...args: any[]) => void): void
    GetSecuritySnapshot(req: any, callback: (err: any, response: any) => void): void
    RequestHistoryKL(req: any, callback: (err: any, response: any) => void): void
  }

  class Futu {
    constructor()
    start(ip: string, port: number, isSSL: boolean, certPath: string | null): void
    close(): void
    onlogin: (ret: number, msg: string) => void
    on(event: string, callback: (...args: any[]) => void): void
    GetSecuritySnapshot(req: any, callback: (err: any, response: any) => void): void
    RequestHistoryKL(req: any, callback: (err: any, response: any) => void): void
  }

  export default Futu
}