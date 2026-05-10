  import { Button, Modal, Select, Stack, TextInput } from '@mantine/core'
  import { useForm } from '@mantine/form'
  import { zodResolver } from 'mantine-form-zod-resolver'
  import { notifications } from '@mantine/notifications'
  import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
  import { z } from 'zod'

  import {
    createCategoryRequest,
    listCategoriesRequest,
    type CategoryRead,
  } from '../api/categories'

  // Mantine Select хранит value как строку. parent_id из формы конвертируем
  // в number | null перед отправкой на бэк (см. mutationFn).
  const categorySchema = z.object({
    name: z.string().min(1, 'Введите название').max(100, 'Максимум 100 символов'),
    parent_id: z.string().nullable(),
  })

  type CategoryFormValues = z.infer<typeof categorySchema>

  interface Props {
    opened: boolean
    onClose: () => void
  }

  // Строит данные для Select из плоского списка категорий: рекурсивно обходит
  // дерево и формирует label с отступом по глубине (unicode-пробелы вместо
  // HTML-индентов — Mantine Select не парсит JSX в label).
  function buildCategoryOptions(
    categories: CategoryRead[],
  ): { value: string; label: string }[] {
    const childrenMap = new Map<number | null, CategoryRead[]>()
    for (const cat of categories) {
      const arr = childrenMap.get(cat.parent_id) ?? []
      arr.push(cat)
      childrenMap.set(cat.parent_id, arr)
    }
    for (const arr of childrenMap.values()) {
      arr.sort((a, b) => a.id - b.id)
    }

    const options: { value: string; label: string }[] = []
    function walk(cat: CategoryRead, depth: number): void {
      options.push({
        value: String(cat.id),
        //   — неразрывный пробел, его HTML/Mantine не схлопывают в один.
        label: '\u00A0\u00A0'.repeat(depth) + cat.name,
      })
      const children = childrenMap.get(cat.id) ?? []
      for (const child of children) walk(child, depth + 1)
    }
    for (const root of childrenMap.get(null) ?? []) walk(root, 0)
    return options
  }

  export function CategoryFormModal({ opened, onClose }: Props) {
    const queryClient = useQueryClient()

    // Для Select-а с возможными родителями нужен список категорий. Используем
    // тот же queryKey, что и страница — Mantine читает из кеша TanStack Query.
    const { data: categories = [] } = useQuery({
      queryKey: ['categories'],
      queryFn: listCategoriesRequest,
    })

    const form = useForm<CategoryFormValues>({
      initialValues: {
        name: '',
        parent_id: null,
      },
      validate: zodResolver(categorySchema),
    })

    const createMutation = useMutation({
      mutationFn: (values: CategoryFormValues) =>
        createCategoryRequest({
          name: values.name,
          parent_id: values.parent_id !== null ? Number(values.parent_id) : null,
        }),
      onSuccess: (data) => {
        notifications.show({
          title: 'Категория создана',
          message: `«${data.name}» добавлена`,
          color: 'green',
        })
        queryClient.invalidateQueries({ queryKey: ['categories'] })
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

    return (
      <Modal opened={opened} onClose={handleClose} title="Новая категория" centered>
        <form onSubmit={form.onSubmit((values) => createMutation.mutate(values))}>
          <Stack>
            <TextInput
              label="Название"
              placeholder="Например, Продукты"
              required
              {...form.getInputProps('name')}
            />
            <Select
              label="Родительская категория"
              description="Выберите, чтобы сделать подкатегорией. Очистите — будет корневой."
              data={buildCategoryOptions(categories)}
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