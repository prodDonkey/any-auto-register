import { useEffect, useState } from 'react'
import { apiFetch } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Save,
  Eye,
  EyeOff,
  Mail,
  Shield,
  Cpu,
  RefreshCw,
  CheckCircle,
  XCircle,
  Server,
} from 'lucide-react'
import { cn } from '@/lib/utils'

type FieldType = 'text' | 'number' | 'toggle' | 'checkbox'

type SettingField = {
  key: string
  label: string
  placeholder?: string
  secret?: boolean
  type?: FieldType
}

type SettingSection = {
  section: string
  desc?: string
  items: SettingField[]
}

const SELECT_FIELDS: Record<string, { label: string; value: string }[]> = {
  mail_provider: [
    { label: 'Laoudo（固定邮箱）', value: 'laoudo' },
    { label: 'TempMail.lol（自动生成）', value: 'tempmail_lol' },
    { label: 'DuckMail（自动生成）', value: 'duckmail' },
    { label: 'MoeMail (sall.cc)', value: 'moemail' },
    { label: 'Freemail（自建 CF Worker）', value: 'freemail' },
    { label: 'CF Worker（自建域名）', value: 'cfworker' },
  ],
  default_executor: [
    { label: 'API 协议（无浏览器）', value: 'protocol' },
    { label: '无头浏览器', value: 'headless' },
    { label: '有头浏览器（调试用）', value: 'headed' },
  ],
  default_captcha_solver: [
    { label: 'YesCaptcha', value: 'yescaptcha' },
    { label: '2Captcha', value: '2captcha' },
    { label: '本地 Solver (Camoufox)', value: 'local_solver' },
    { label: '手动', value: 'manual' },
  ],
}

const TABS: { id: string; label: string; icon: any; sections: SettingSection[] }[] = [
  {
    id: 'register', label: '注册设置', icon: Cpu,
    sections: [{
      section: '默认注册方式',
      desc: '控制注册任务如何执行',
      items: [
        { key: 'default_executor', label: '执行器类型' },
      ],
    }],
  },
  {
    id: 'mailbox', label: '邮箱服务', icon: Mail,
    sections: [{
      section: '默认邮箱服务',
      desc: '选择注册时使用的邮箱类型',
      items: [
        { key: 'mail_provider', label: '邮箱服务' },
      ],
    }, {
      section: 'Laoudo',
      desc: '固定邮箱，手动配置',
      items: [
        { key: 'laoudo_email', label: '邮箱地址', placeholder: 'xxx@laoudo.com' },
        { key: 'laoudo_account_id', label: 'Account ID', placeholder: '563' },
        { key: 'laoudo_auth', label: 'JWT Token', placeholder: 'eyJ...', secret: true },
      ],
    }, {
      section: 'Freemail',
      desc: '基于 Cloudflare Worker 的自建邮箱，支持管理员令牌或账号密码认证',
      items: [
        { key: 'freemail_api_url', label: 'API URL', placeholder: 'https://mail.example.com' },
        { key: 'freemail_admin_token', label: '管理员令牌', secret: true },
        { key: 'freemail_username', label: '用户名（可选）', placeholder: '' },
        { key: 'freemail_password', label: '密码（可选）', secret: true },
      ],
    }, {
      section: 'MoeMail',
      desc: '自动注册账号并生成临时邮箱，默认无需配置',
      items: [
        { key: 'moemail_api_url', label: 'API URL', placeholder: 'https://sall.cc' },
      ],
    }, {
      section: 'TempMail.lol',
      desc: '自动生成邮箱，无需配置，需要代理访问（CN IP 被封）',
      items: [],
    }, {
      section: 'DuckMail',
      desc: '自动生成邮箱，随机创建账号（默认无需配置）',
      items: [
        { key: 'duckmail_api_url', label: 'Web URL', placeholder: 'https://www.duckmail.sbs' },
        { key: 'duckmail_provider_url', label: 'Provider URL', placeholder: 'https://api.duckmail.sbs' },
        { key: 'duckmail_bearer', label: 'Bearer Token', placeholder: 'kevin273945', secret: true },
      ],
    }, {
      section: 'CF Worker 自建邮箱',
      desc: '基于 Cloudflare Worker 的自建临时邮箱服务',
      items: [
        { key: 'cfworker_api_url', label: 'API URL', placeholder: 'https://apimail.example.com' },
        { key: 'cfworker_admin_token', label: '管理员 Token', secret: true },
        { key: 'cfworker_domain', label: '邮箱域名', placeholder: 'example.com' },
        { key: 'cfworker_fingerprint', label: 'Fingerprint', placeholder: '6703363b...' },
      ],
    }],
  },
  {
    id: 'captcha', label: '验证码', icon: Shield,
    sections: [{
      section: '验证码服务',
      desc: '用于绕过注册页面的人机验证',
      items: [
        { key: 'default_captcha_solver', label: '默认服务' },
        { key: 'yescaptcha_key', label: 'YesCaptcha Key', secret: true },
        { key: 'twocaptcha_key', label: '2Captcha Key', secret: true },
      ],
    }],
  },
  {
    id: 'chatgpt', label: 'ChatGPT', icon: Shield,
    sections: [{
      section: 'CPA 面板',
      desc: '注册完成后自动上传到 CPA 管理平台',
      items: [
        { key: 'cpa_api_url', label: 'API URL', placeholder: 'https://your-cpa.example.com' },
        { key: 'cpa_api_key', label: 'API Key', secret: true },
      ],
    }, {
      section: 'Team Manager',
      desc: '上传到自建 Team Manager 系统',
      items: [
        { key: 'team_manager_url', label: 'API URL', placeholder: 'https://your-tm.example.com' },
        { key: 'team_manager_key', label: 'API Key', secret: true },
      ],
    }],
  },
  {
    id: 'sub2api', label: 'Sub2Api', icon: Server,
    sections: [{
      section: 'Sync 服务',
      desc: 'any-auto-register 通过独立 Sync 服务把账号同步到 Sub2Api',
      items: [
        { key: 'sub2api_sync_url', label: 'Sync URL', placeholder: 'http://127.0.0.1:18521/sync' },
      ],
    }, {
      section: '平台认证',
      desc: '保存后用于登录 Sub2Api 并自动获取 Bearer Token',
      items: [
        { key: 'sub2api_base_url', label: '平台地址', placeholder: 'http://106.53.27.215:8080' },
        { key: 'sub2api_admin_email', label: '管理员邮箱', placeholder: 'admin@example.com' },
        { key: 'sub2api_admin_password', label: '密码', secret: true, placeholder: '请输入密码' },
      ],
    }, {
      section: '同步策略',
      desc: '控制注册完成后是否自动同步以及账号池目标阈值',
      items: [
        { key: 'sub2api_auto_sync', label: '注册后自动导入', type: 'toggle' },
        { key: 'sub2api_min_candidates', label: '目标阈值', type: 'number', placeholder: '200' },
      ],
    }, {
      section: '自动维护',
      desc: '后台调度器会按间隔执行维护动作',
      items: [
        { key: 'sub2api_auto_maintain', label: '自动维护', type: 'toggle' },
        { key: 'sub2api_maintain_interval_minutes', label: '维护间隔(分钟)', type: 'number', placeholder: '30' },
      ],
    }, {
      section: '维护动作',
      desc: '手动维护和自动维护都会按勾选项执行',
      items: [
        { key: 'sub2api_maintain_refresh_abnormal_accounts', label: '异常账号测活', type: 'checkbox' },
        { key: 'sub2api_maintain_delete_abnormal_accounts', label: '删除仍异常账号', type: 'checkbox' },
        { key: 'sub2api_maintain_dedupe_duplicate_accounts', label: '重复账号清理', type: 'checkbox' },
      ],
    }],
  },
]

const isTruthy = (value: unknown) => ['1', 'true', 'yes', 'on'].includes(String(value ?? '').trim().toLowerCase())

function Field({ field, form, setForm, showSecret, setShowSecret }: any) {
  const { key, label, placeholder, secret, type } = field
  const options = SELECT_FIELDS[key]
  const value = form[key] ?? ''

  if (type === 'toggle') {
    const checked = isTruthy(value)
    return (
      <div className="flex items-center justify-between py-3 border-b border-white/5 last:border-0">
        <div>
          <div className="text-sm text-[var(--text-primary)] font-medium">{label}</div>
        </div>
        <label className="inline-flex items-center gap-3 cursor-pointer">
          <span className="text-xs text-[var(--text-muted)]">{checked ? '已开启' : '已关闭'}</span>
          <input
            type="checkbox"
            checked={checked}
            onChange={e => setForm((f: any) => ({ ...f, [key]: e.target.checked ? '1' : '0' }))}
            className="h-4 w-4 accent-indigo-500"
          />
        </label>
      </div>
    )
  }

  if (type === 'checkbox') {
    const checked = isTruthy(value)
    return (
      <label className="flex items-center gap-3 py-3 border-b border-white/5 last:border-0 cursor-pointer">
        <input
          type="checkbox"
          checked={checked}
          onChange={e => setForm((f: any) => ({ ...f, [key]: e.target.checked ? '1' : '0' }))}
          className="h-4 w-4 accent-indigo-500"
        />
        <span className="text-sm text-[var(--text-primary)]">{label}</span>
      </label>
    )
  }

  return (
    <div className="grid grid-cols-3 gap-4 items-center py-3 border-b border-white/5 last:border-0">
      <label className="text-sm text-[var(--text-secondary)] font-medium">{label}</label>
      <div className="col-span-2 relative">
        {options ? (
          <select
            value={value || options[0].value}
            onChange={e => setForm((f: any) => ({ ...f, [key]: e.target.value }))}
            className="w-full bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-primary)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 appearance-none"
          >
            {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        ) : (
          <>
            <input
              type={secret && !showSecret[key] ? 'password' : (type === 'number' ? 'number' : 'text')}
              value={String(value)}
              onChange={e => setForm((f: any) => ({ ...f, [key]: e.target.value }))}
              placeholder={placeholder}
              className="w-full bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-primary)] rounded-lg px-3 py-2 text-sm pr-10 focus:outline-none focus:border-indigo-500 placeholder:text-[var(--text-muted)]"
            />
            {secret && (
              <button
                type="button"
                onClick={() => setShowSecret((s: any) => ({ ...s, [key]: !s[key] }))}
                className="absolute right-3 top-2.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              >
                {showSecret[key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  const [activeTab, setActiveTab] = useState('register')
  const [form, setForm] = useState<Record<string, string>>({})
  const [showSecret, setShowSecret] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [solverRunning, setSolverRunning] = useState<boolean | null>(null)
  const [sub2apiTesting, setSub2apiTesting] = useState(false)
  const [sub2apiStatus, setSub2apiStatus] = useState('')

  useEffect(() => {
    apiFetch('/config').then((data) => {
      setForm({
        sub2api_auto_sync: '0',
        sub2api_min_candidates: '200',
        sub2api_auto_maintain: '0',
        sub2api_maintain_interval_minutes: '30',
        sub2api_maintain_refresh_abnormal_accounts: '1',
        sub2api_maintain_delete_abnormal_accounts: '1',
        sub2api_maintain_dedupe_duplicate_accounts: '1',
        ...data,
      })
    })
  }, [])

  const checkSolver = async () => {
    try {
      const d = await apiFetch('/solver/status')
      setSolverRunning(d.running)
    } catch {
      setSolverRunning(false)
    }
  }

  const restartSolver = async () => {
    await apiFetch('/solver/restart', { method: 'POST' })
    setSolverRunning(null)
    setTimeout(checkSolver, 4000)
  }

  useEffect(() => { checkSolver() }, [])

  const save = async () => {
    setSaving(true)
    try {
      await apiFetch('/config', { method: 'PUT', body: JSON.stringify({ data: form }) })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  const testSub2Api = async () => {
    setSub2apiTesting(true)
    setSub2apiStatus('正在测试连接...')
    try {
      const data = await apiFetch('/sub2api/test', {
        method: 'POST',
        body: JSON.stringify({
          sync_url: form.sub2api_sync_url || '',
          base_url: form.sub2api_base_url || '',
          bearer_token: form.sub2api_bearer_token || '',
          admin_email: form.sub2api_admin_email || '',
          admin_password: form.sub2api_admin_password || '',
        }),
      })
      setSub2apiStatus(data.message || (data.ok ? '连接成功' : '连接失败'))
    } catch (error: any) {
      setSub2apiStatus(error?.message || '连接失败')
    } finally {
      setSub2apiTesting(false)
    }
  }

  const tab = TABS.find(t => t.id === activeTab)!
  const isSub2ApiTab = activeTab === 'sub2api'

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">全局配置</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">配置将持久化保存，注册任务自动使用</p>
      </div>

      <div className="flex gap-6">
        <div className="w-44 shrink-0 space-y-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={cn(
                'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                activeTab === id
                  ? 'bg-indigo-600/20 text-[var(--text-accent)] font-medium'
                  : 'text-[var(--text-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-primary)]',
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}

          <div className="mt-4 pt-4 border-t border-[var(--border)]">
            <p className="text-xs text-[var(--text-muted)] px-3 mb-2">Turnstile Solver</p>
            <div className="px-3 flex items-center gap-2">
              {solverRunning === null
                ? <RefreshCw className="h-3 w-3 animate-spin text-[var(--text-muted)]" />
                : solverRunning
                  ? <CheckCircle className="h-3 w-3 text-emerald-400" />
                  : <XCircle className="h-3 w-3 text-red-400" />}
              <span className={cn('text-xs', solverRunning ? 'text-emerald-400' : 'text-[var(--text-muted)]')}>
                {solverRunning === null ? '检测中' : solverRunning ? '运行中' : '未运行'}
              </span>
            </div>
            <button
              onClick={restartSolver}
              className="mt-2 w-full text-xs px-3 py-1.5 text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-hover)] rounded-lg text-left"
            >
              重启 Solver
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-4">
          {tab.sections.map(({ section, desc, items }) => (
            <div key={section} className="bg-white/[0.03] border border-[var(--border)] rounded-xl p-5">
              <div className="mb-4">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{section}</h3>
                {desc && <p className="text-xs text-[var(--text-muted)] mt-0.5">{desc}</p>}
              </div>
              {items.length === 0 ? (
                <div className="text-sm text-[var(--text-muted)]">当前无需配置</div>
              ) : items.map((field) => (
                <Field
                  key={field.key}
                  field={field}
                  form={form}
                  setForm={setForm}
                  showSecret={showSecret}
                  setShowSecret={setShowSecret}
                />
              ))}
              {isSub2ApiTab && section === '平台认证' && (
                <div className="pt-4 flex items-center gap-3">
                  <Button variant="outline" onClick={testSub2Api} disabled={sub2apiTesting}>
                    {sub2apiTesting ? '测试中...' : '测试连接'}
                  </Button>
                  {sub2apiStatus && (
                    <p className="text-sm text-[var(--text-muted)]">{sub2apiStatus}</p>
                  )}
                </div>
              )}
            </div>
          ))}

          {isSub2ApiTab ? (
            <Button onClick={save} disabled={saving} className="w-full">
              <Save className="h-4 w-4 mr-2" />
              {saved ? '已保存 ✓' : saving ? '保存中...' : '保存配置'}
            </Button>
          ) : (
            <Button onClick={save} disabled={saving} className="w-full">
              <Save className="h-4 w-4 mr-2" />
              {saved ? '已保存 ✓' : saving ? '保存中...' : '保存配置'}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
