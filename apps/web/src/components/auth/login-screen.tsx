"use client";

import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  UserRound
} from "lucide-react";
import { useState } from "react";

import { LoginDataScene } from "@/components/auth/login-data-scene";

import styles from "./login-screen.module.css";

interface LoginScreenProps {
  busy: boolean;
  error: string | null;
  onSubmit: (loginName: string, password: string) => Promise<void>;
}

export function LoginScreen({ busy, error, onSubmit }: LoginScreenProps) {
  const [loginName, setLoginName] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);

  return (
    <main className={styles.screen}>
      <LoginDataScene />
      <div aria-hidden="true" className={styles.visualShade} />

      <header className={styles.brand}>
        <span className={styles.brandSymbol}>知</span>
        <span className={styles.brandCopy}>
          <strong>知行数枢</strong>
          <small>ZHIXING DATA INTELLIGENCE</small>
        </span>
      </header>

      <section className={styles.sceneIdentity} aria-label="产品名称">
        <p>ENTERPRISE INTELLIGENCE CORE</p>
        <h1>知行数枢</h1>
        <span>企业数据智能运营中枢</span>
      </section>

      <div className={styles.sceneStatus}>
        <span aria-hidden="true" />
        <strong>数据空间在线</strong>
        <small>PRIVATE CLOUD</small>
      </div>

      <aside className={styles.accessShell}>
        <div className={styles.accessInner}>
          <div className={styles.accessHeading}>
            <span>ENTERPRISE ACCESS</span>
            <h2>企业账号登录</h2>
          </div>

          <form
            className={styles.form}
            onSubmit={(event) => {
              event.preventDefault();
              void onSubmit(loginName, password).catch(() => undefined);
            }}
          >
            <label className={styles.field}>
              <span>登录名</span>
              <span className={styles.inputShell}>
                <UserRound aria-hidden="true" size={17} />
                <input
                  autoComplete="username"
                  autoFocus
                  onChange={(event) => setLoginName(event.target.value)}
                  placeholder="输入企业登录名"
                  required
                  value={loginName}
                />
              </span>
            </label>

            <label className={styles.field}>
              <span>密码</span>
              <span className={styles.inputShell}>
                <LockKeyhole aria-hidden="true" size={17} />
                <input
                  autoComplete="current-password"
                  minLength={12}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="输入账号密码"
                  required
                  type={passwordVisible ? "text" : "password"}
                  value={password}
                />
                <button
                  aria-label={passwordVisible ? "隐藏密码" : "显示密码"}
                  className={styles.passwordToggle}
                  onClick={(event) => {
                    event.preventDefault();
                    setPasswordVisible((visible) => !visible);
                  }}
                  title={passwordVisible ? "隐藏密码" : "显示密码"}
                  type="button"
                >
                  {passwordVisible ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </span>
            </label>

            {error ? <div className={styles.error} role="alert">{error}</div> : null}

            <button
              className={styles.submit}
              disabled={busy || loginName.trim().length < 3 || password.length < 12}
              type="submit"
            >
              <span>{busy ? "正在登录" : "进入数枢"}</span>
              {busy ? <LoaderCircle className="spinning" size={18} /> : <ArrowRight size={18} />}
            </button>
          </form>

          <div className={styles.sessionState}>
            <ShieldCheck aria-hidden="true" size={16} />
            <span>私有化部署</span>
            <i aria-hidden="true" />
            <span>企业身份会话</span>
          </div>
        </div>

        <footer className={styles.accessFooter}>
          <span>ZHIXING / ACCESS NODE 01</span>
          <span className={styles.online}><i aria-hidden="true" /> ONLINE</span>
        </footer>
      </aside>
    </main>
  );
}
