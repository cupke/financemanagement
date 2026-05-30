    import { useEffect } from 'react'
    import {
      Button,
      Modal,
      SegmentedControl,
      Select,
      Stack,
      TextInput,
    } from '@mantine/core'
    import { useForm } from '@mantine/form'
    import { zodResolver } from 'mantine-form-zod-resolver'
    import { notifications } from '@mantine/notifications'
    import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
    import { z } from 'zod'

    import {
      createCategoryRequest,
      listCategoriesRequest,
      updateCategoryRequest,
      type CategoryKind,
      type CategoryRead,
    } from '../api/categories'
    import { buildCategoryOptions } from '../lib/categoryTree'

    // Mantine Select хранит value как строку. parent_id из формы конвертируем
    // в number | null перед отправкой на бэк (см. mutationFn).
    const categorySchema = z.object({
      name: z.string().min(1, 'Введите название').max(100, 'Максимум 100 символов'),
      kind: z.enum(['income', 'expense']),
      parent_id: z.string().nullable(),
    })

    type CategoryFormValues = z.infer<typeof categorySchema>

    interface Props {
      opened: boolean
      onClose: () => void
      // С каким kind открыть форму создания. Если не передан — 'expense' (расход
      // более частый сценарий в финансовом приложении). В режиме редактирования
      // игнорируется: kind берётся из редактируемой категории и не меняется.
      initialKind?: CategoryKind
      // Зафиксировать kind — скрыть SegmentedControl выбора типа.
      // Используется, например, в форме транзакции: тип операции уже выбран,
      // показывать переключатель тут было бы избыточно и сбивало бы с толку.
      lockKind?: boolean
      // Опциональный колбэк: вызывается после успешного создания категории
      // с объектом созданной категории. Используется, например, в форме
      // транзакции, чтобы автоматически выбрать только что созданную категорию.
      onCreated?: (category: CategoryRead) => void
      // Если передан — модалка работает в режиме РЕДАКТИРОВАНИЯ этой категории
      // (PATCH вместо POST). Меняются имя и родитель; тип (kind) менять нельзя —
      // бэк это запрещает (сменился бы тип у уже привязанных операций).
      category?: CategoryRead | null
    }

    // Собрать id самой категории и всех её потомков (любой глубины). Нужно, чтобы
    // в режиме редактирования исключить их из списка возможных родителей: нельзя
    // перенести категорию ни в саму себя, ни в собственное поддерево (это создало
    // бы цикл — бэк такое отвергает, но и предлагать в UI не стоит).
    function collectSubtreeIds(
      rootId: number,
      categories: CategoryRead[],
    ): Set<number> {
      const childrenOf = new Map<number, number[]>()
      for (const c of categories) {
        if (c.parent_id !== null) {
          const arr = childrenOf.get(c.parent_id) ?? []
          arr.push(c.id)
          childrenOf.set(c.parent_id, arr)
        }
      }
      const result = new Set<number>([rootId])
      const queue = [rootId]
      while (queue.length > 0) {
        const current = queue.shift() as number
        for (const childId of childrenOf.get(current) ?? []) {
          if (!result.has(childId)) {
            result.add(childId)
            queue.push(childId)
          }
        }
      }
      return result
    }

   export function CategoryFormModal({
      opened,
      onClose,
      initialKind = 'expense',
      lockKind = false,
      onCreated,
      category,
    }: Props) {
      const queryClient = useQueryClient()
      const isEditing = !!category

      // Список всех категорий — для Select родителя. Один общий кеш с другими
      // компонентами; фильтрацию по kind делаем уже в buildCategoryOptions ниже.
      const { data: categories = [] } = useQuery({
        queryKey: ['categories'],
        queryFn: () => listCategoriesRequest(),
      })

      const form = useForm<CategoryFormValues>({
        initialValues: {
          name: '',
          kind: initialKind,
          parent_id: null,
        },
        validate: zodResolver(categorySchema),
      })

      // При смене kind в форме сбрасываем выбранный parent_id — старый
      // родитель мог быть другого типа и стать невалидным. В режиме
      // редактирования kind заблокирован, поэтому эффект не нужен (и сбросил бы
      // предзаполненного родителя).
      useEffect(() => {
        if (isEditing) return
        form.setFieldValue('parent_id', null)
        // form в deps намеренно опущен — иначе бесконечный цикл.
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [form.values.kind])

      // При открытии модалки синхронизируем форму: в режиме редактирования —
      // значениями категории, в режиме создания — пустыми с нужным initialKind.
      useEffect(() => {
        if (!opened) return
        if (category) {
          form.setValues({
            name: category.name,
            kind: category.kind,
            parent_id:
              category.parent_id !== null ? String(category.parent_id) : null,
          })
        } else {
          form.setValues({ name: '', kind: initialKind, parent_id: null })
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [opened, category?.id, initialKind])

      const createMutation = useMutation({
        mutationFn: (values: CategoryFormValues) =>
          createCategoryRequest({
            name: values.name,
            kind: values.kind,
            parent_id: values.parent_id !== null ? Number(values.parent_id) : null,
          }),
        onSuccess: (data) => {
          notifications.show({
            title: 'Категория создана',
            message: `«${data.name}» добавлена`,
            color: 'green',
          })
          queryClient.invalidateQueries({ queryKey: ['categories'] })
          onCreated?.(data)
          form.reset()
          onClose()
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onError: (error: any) => {
          const raw = error.response?.data?.detail
          const message =
            typeof raw === 'string'
              ? raw
              : Array.isArray(raw)
                ? raw.map((e) => e.msg).join('; ')
                : 'Не удалось создать категорию'
          notifications.show({
            title: 'Ошибка',
            message,
            color: 'red',
          })
        },
      })

      const updateMutation = useMutation({
        mutationFn: (values: CategoryFormValues) =>
          updateCategoryRequest(category!.id, {
            name: values.name,
            parent_id: values.parent_id !== null ? Number(values.parent_id) : null,
          }),
        onSuccess: (data) => {
          notifications.show({
            title: 'Категория обновлена',
            message: `«${data.name}» сохранена`,
            color: 'green',
          })
          // Имя/родитель влияют на подписи и группировки в зависимых виджетах:
          // отчёты и дашборд показывают имя категории, а бюджет на родителя
          // агрегирует траты по всему поддереву (перенос меняет состав поддерева).
          queryClient.invalidateQueries({ queryKey: ['categories'] })
          queryClient.invalidateQueries({ queryKey: ['transactions'] })
          queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
          queryClient.invalidateQueries({ queryKey: ['reports-overview'] })
          queryClient.invalidateQueries({ queryKey: ['budgets'] })
          onClose()
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        onError: (error: any) => {
          const raw = error.response?.data?.detail
          const message =
            typeof raw === 'string'
              ? raw
              : Array.isArray(raw)
                ? raw.map((e) => e.msg).join('; ')
                : 'Не удалось сохранить категорию'
          notifications.show({
            title: 'Ошибка',
            message,
            color: 'red',
          })
        },
      })

      const handleClose = () => {
        form.reset()
        onClose()
      }

      // Список родителей — только те, что совпадают по kind. Нельзя положить
      // «Зарплату» (доход) в «Продукты» (расход). В режиме редактирования kind
      // фиксирован, в режиме создания берётся из текущего выбора формы.
      const kindForParents = isEditing ? category!.kind : form.values.kind
      let parentOptions = buildCategoryOptions(categories, kindForParents)
      // В режиме редактирования убираем саму категорию и её потомков — перенос
      // туда создал бы цикл.
      if (isEditing) {
        const excluded = collectSubtreeIds(category!.id, categories)
        parentOptions = parentOptions.filter(
          (o) => !excluded.has(Number(o.value)),
        )
      }

      const submitMutation = isEditing ? updateMutation : createMutation

      return (
        <Modal
          opened={opened}
          onClose={handleClose}
          title={isEditing ? 'Редактирование категории' : 'Новая категория'}
          centered
        >
          <form onSubmit={form.onSubmit((values) => submitMutation.mutate(values))}>
            <Stack>
              {!lockKind && (
                <SegmentedControl
                  fullWidth
                  data={[
                    { label: '💸 Расход', value: 'expense' },
                    { label: '💰 Доход', value: 'income' },
                  ]}
                  // Тип нельзя менять у существующей категории (бэк запрещает).
                  disabled={isEditing}
                  {...form.getInputProps('kind')}
                />
              )}
              <TextInput
                label="Название"
                placeholder="Например, Продукты"
                required
                {...form.getInputProps('name')}
              />
              <Select
                label="Родительская категория"
                description="Выберите, чтобы сделать подкатегорией. Очистите — будет корневой."
                data={parentOptions}
                placeholder="— Без родителя (корневая) —"
                clearable
                searchable
                {...form.getInputProps('parent_id')}
              />
              <Button type="submit" loading={submitMutation.isPending}>
                {isEditing ? 'Сохранить' : 'Создать'}
              </Button>
            </Stack>
          </form>
        </Modal>
      )
    }
