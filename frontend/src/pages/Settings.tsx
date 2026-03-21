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

type MailProviderDefinition = {
  name: string
  label: string
  desc?: string
  fields: SettingField[]
}

const SELECT_FIELDS: Record<string, { label: string; value: string }[]> = {
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

const MAIL_STRATEGY_OPTIONS = [
  { label: '轮询', value: 'round_robin' },
  { label: '随机', value: 'random' },
  { label: '容错优先', value: 'failover' },
]

const MAIL_PROVIDER_DEFINITIONS: MailProviderDefinition[] = [
  {
    name: 'tempmail_lol',
    label: 'TempMail.lol（自动生成）',
    desc: '免费临时邮箱，无需注册账号',
    fields: [
      { key: 'api_url', label: 'API URL', placeholder: 'https://api.tempmail.lol/v2' },
    ],
  },
  {
    name: 'moemail',
    label: 'MoeMail（自动生成）',
    desc: '自动注册临时账号并生成邮箱',
    fields: [
      { key: 'api_url', label: 'API URL', placeholder: 'https://sall.cc' },
    ],
  },
  {
    name: 'duckmail',
    label: 'DuckMail（Bearer Token）',
    desc: '优先使用原生 API，旧版包装层参数仅用于兼容',
    fields: [
      { key: 'api_url', label: 'API URL', placeholder: 'https://api.duckmail.sbs' },
      { key: 'provider_url', label: 'Legacy Provider URL', placeholder: 'https://api.duckmail.sbs' },
      { key: 'bearer_token', label: 'Legacy Bearer Token', secret: true, placeholder: 'DuckMail Bearer Token' },
    ],
  },
  {
    name: 'freemail',
    label: 'Freemail（自建）',
    desc: '支持管理员令牌或账号密码认证',
    fields: [
      { key: 'api_url', label: 'API URL', placeholder: 'https://mail.example.com' },
      { key: 'admin_token', label: '管理员令牌', secret: true, placeholder: 'Admin Token' },
      { key: 'username', label: '用户名（可选）', placeholder: '' },
      { key: 'password', label: '密码（可选）', secret: true, placeholder: '' },
    ],
  },
  {
    name: 'cfworker',
    label: 'Cloudflare Temp Email',
    desc: '基于 Cloudflare Worker 的自建临时邮箱',
    fields: [
      { key: 'api_url', label: 'API URL', placeholder: 'https://apimail.example.com' },
      { key: 'admin_token', label: 'Admin Token', secret: true, placeholder: 'x-admin-auth' },
      { key: 'domain', label: '域名', placeholder: 'example.com' },
      { key: 'fingerprint', label: 'Fingerprint（可选）', placeholder: '6703363b...' },
    ],
  },
  {
    name: 'laoudo',
    label: 'Laoudo（固定邮箱）',
    desc: '使用固定邮箱地址和 Account ID',
    fields: [
      { key: 'email', label: '邮箱地址', placeholder: 'xxx@laoudo.com' },
      { key: 'account_id', label: 'Account ID', placeholder: '563' },
      { key: 'auth_token', label: 'JWT Token', secret: true, placeholder: 'eyJ...' },
    ],
  },
]

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
    sections: [],
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
  const [form, setForm] = useState<Record<string, any>>({})
  const [showSecret, setShowSecret] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [solverRunning, setSolverRunning] = useState<boolean | null>(null)
  const [mailConfig, setMailConfig] = useState<Record<string, any>>({
    mail_providers: [],
    mail_provider_configs: {},
    mail_strategy: 'round_robin',
  })
  const [mailSaving, setMailSaving] = useState(false)
  const [mailTesting, setMailTesting] = useState(false)
  const [mailStatus, setMailStatus] = useState('')
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
    apiFetch('/mail/config').then((data) => {
      setMailConfig({
        mail_providers: Array.isArray(data.mail_providers) ? data.mail_providers : [],
        mail_provider_configs: data.mail_provider_configs || {},
        mail_strategy: data.mail_strategy || 'round_robin',
      })
    }).catch(() => {})
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

  const updateMailProviderChecked = (provider: string, checked: boolean) => {
    setMailConfig((prev: any) => {
      const current = Array.isArray(prev.mail_providers) ? [...prev.mail_providers] : []
      const nextProviders = checked
        ? (current.includes(provider) ? current : [...current, provider])
        : current.filter((name: string) => name !== provider)
      return {
        ...prev,
        mail_providers: nextProviders,
      }
    })
  }

  const updateMailProviderField = (provider: string, key: string, value: string) => {
    setMailConfig((prev: any) => ({
      ...prev,
      mail_provider_configs: {
        ...(prev.mail_provider_configs || {}),
        [provider]: {
          ...((prev.mail_provider_configs || {})[provider] || {}),
          [key]: value,
        },
      },
    }))
  }

  const saveMailConfig = async () => {
    setMailSaving(true)
    try {
      const providers = Array.isArray(mailConfig.mail_providers) ? mailConfig.mail_providers : []
      if (providers.length === 0) {
        setMailStatus('请至少选择一个邮箱提供商')
        return false
      }
      await apiFetch('/mail/config', {
        method: 'POST',
        body: JSON.stringify({
          mail_providers: providers,
          mail_provider_configs: mailConfig.mail_provider_configs || {},
          mail_strategy: mailConfig.mail_strategy || 'round_robin',
        }),
      })
      setMailStatus('配置已保存')
      return true
    } catch (error: any) {
      setMailStatus(error?.message || '保存失败')
      return false
    } finally {
      setMailSaving(false)
    }
  }

  const testMailConfig = async () => {
    setMailTesting(true)
    setMailStatus('测试中...')
    try {
      const savedOk = await saveMailConfig()
      if (!savedOk) return
      const data = await apiFetch('/mail/test', { method: 'POST' })
      if (Array.isArray(data.results)) {
        const msg = data.results.map((item: any) => `${item.provider}: ${item.ok ? 'OK' : item.message}`).join(' | ')
        setMailStatus(msg || (data.ok ? '连接成功' : '连接失败'))
      } else {
        setMailStatus(data.message || (data.ok ? '连接成功' : '连接失败'))
      }
    } catch (error: any) {
      setMailStatus(error?.message || '连接失败')
    } finally {
      setMailTesting(false)
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
  const isMailboxTab = activeTab === 'mailbox'
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
          {isMailboxTab ? (
            <div className="space-y-4">
              <div className="bg-white/[0.03] border border-[var(--border)] rounded-xl p-5">
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">邮箱提供商</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">可同时勾选多个邮箱提供商，注册时按策略选择</p>
                </div>
                <div className="space-y-3">
                  {MAIL_PROVIDER_DEFINITIONS.map((provider) => {
                    const checked = (mailConfig.mail_providers || []).includes(provider.name)
                    const providerCfg = (mailConfig.mail_provider_configs || {})[provider.name] || {}
                    return (
                      <div key={provider.name} className="border border-[var(--border)] rounded-xl overflow-hidden bg-[var(--bg-hover)]/40">
                        <label className="flex items-center gap-3 px-4 py-3 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={e => updateMailProviderChecked(provider.name, e.target.checked)}
                            className="h-4 w-4 accent-indigo-500"
                          />
                          <div className="flex-1">
                            <div className="text-sm font-medium text-[var(--text-primary)]">{provider.label}</div>
                            {provider.desc && <div className="text-xs text-[var(--text-muted)] mt-0.5">{provider.desc}</div>}
                          </div>
                        </label>
                        {checked && provider.fields.length > 0 && (
                          <div className="border-t border-[var(--border)] px-4 py-3 space-y-3">
                            {provider.fields.map((field) => {
                              const value = providerCfg[field.key] ?? ''
                              const secretKey = `${provider.name}:${field.key}`
                              return (
                                <div key={field.key} className="grid grid-cols-3 gap-4 items-center">
                                  <label className="text-sm text-[var(--text-secondary)] font-medium">{field.label}</label>
                                  <div className="col-span-2 relative">
                                    <input
                                      type={field.secret && !showSecret[secretKey] ? 'password' : (field.type === 'number' ? 'number' : 'text')}
                                      value={String(value)}
                                      onChange={e => updateMailProviderField(provider.name, field.key, e.target.value)}
                                      placeholder={field.placeholder}
                                      className="w-full bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-primary)] rounded-lg px-3 py-2 text-sm pr-10 focus:outline-none focus:border-indigo-500 placeholder:text-[var(--text-muted)]"
                                    />
                                    {field.secret && (
                                      <button
                                        type="button"
                                        onClick={() => setShowSecret((s) => ({ ...s, [secretKey]: !s[secretKey] }))}
                                        className="absolute right-3 top-2.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                                      >
                                        {showSecret[secretKey] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                      </button>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="bg-white/[0.03] border border-[var(--border)] rounded-xl p-5">
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-[var(--text-primary)]">路由策略</h3>
                  <p className="text-xs text-[var(--text-muted)] mt-0.5">控制注册时如何从多个邮箱提供商中选取一个</p>
                </div>
                <select
                  value={mailConfig.mail_strategy || 'round_robin'}
                  onChange={e => setMailConfig((prev: any) => ({ ...prev, mail_strategy: e.target.value }))}
                  className="w-full max-w-xs bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-primary)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-indigo-500"
                >
                  {MAIL_STRATEGY_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-3">
                <Button variant="outline" onClick={testMailConfig} disabled={mailTesting || mailSaving}>
                  {mailTesting ? '测试中...' : '测试连接'}
                </Button>
                <Button onClick={saveMailConfig} disabled={mailSaving || mailTesting} className="flex-1">
                  <Save className="h-4 w-4 mr-2" />
                  {mailSaving ? '保存中...' : '保存'}
                </Button>
              </div>
              {mailStatus && <p className="text-sm text-[var(--text-muted)]">{mailStatus}</p>}
            </div>
          ) : (
            <>
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
            </>
          )}

          {isMailboxTab ? null : isSub2ApiTab ? (
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
