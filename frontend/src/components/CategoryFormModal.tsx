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
      // С каким kind открыть форму. Если не передан — 'expense' (расход
      // более частый сценарий в финансовом приложении).
      initialKind?: CategoryKind
      // Зафиксировать kind — скрыть SegmentedControl выбора типа.
      // Используется, например, в форме транзакции: тип операции уже выбран,
      // показывать переключатель тут было бы избыточно и сбивало бы с толку.
      lockKind?: boolean
      // Опциональный колбэк: вызывается после успешного создания категории
      // с объектом созданной категории. Используется, например, в форме
      // транзакции, чтобы автоматически выбрать только что созданную категорию.
      onCreated?: (category: CategoryRead) => void
    }

   export function CategoryFormModal({
      opened,
      onClose,
      initialKind = 'expense',
      lockKind = false,
      onCreated,
    }: Props) {
      const queryClient = useQueryClient()
  
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
      // родитель мог быть другого типа и стать невалидным.
      useEffect(() => {
        form.setFieldValue('parent_id', null)
        // form в deps намеренно опущен — иначе бесконечный цикл.
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [form.values.kind])
  
      // При повторном открытии модалки с другим initialKind — синхронизируем форму.
      useEffect(() => {
        if (opened) {
          form.setFieldValue('kind', initialKind)
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
      }, [opened, initialKind])
  
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
  
      const handleClose = () => {
        form.reset()
        onClose()
      }

      // Список родителей — только те, что совпадают по kind с текущим выбором
      // в форме. Нельзя положить «Зарплату» (доход) в «Продукты» (расход).
      const parentOptions = buildCategoryOptions(categories, form.values.kind)

      return (
        <Modal opened={opened} onClose={handleClose} title="Новая категория" centered>
          <form onSubmit={form.onSubmit((values) => createMutation.mutate(values))}>
            <Stack>
              {!lockKind && (
                <SegmentedControl
                  fullWidth
                  data={[
                    { label: '💸 Расход', value: 'expense' },
                    { label: '💰 Доход', value: 'income' },
                  ]}
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
              <Button type="submit" loading={createMutation.isPending}>
                Создать
              </Button>
            </Stack>
          </form>
        </Modal>
      )
    }