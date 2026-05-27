import { useEffect } from 'react'
import {
  Button,
  Modal,
  NumberInput,
  Select,
  Stack,
  Text,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { zodResolver } from 'mantine-form-zod-resolver'
import { notifications } from '@mantine/notifications'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { z } from 'zod'

import {
  createBudgetRequest,
  updateBudgetRequest,
  type BudgetWithProgress,
} from '../api/budgets'
import { listCategoriesRequest } from '../api/categories'
import { buildCategoryOptions } from '../lib/categoryTree'

// Mantine Select хранит value как строку. category_id конвертируем
// в number перед отправкой на бэк.
// Для amount используем preprocess: NumberInput при пустом поле возвращает '',
// а Zod ждёт number — без preprocess валидация на пустом поле падает невнятным
// «Expected number, received string» вместо понятного «Введите сумму».
const budgetSchema = z.object({
  category_id: z.string().min(1, 'Выберите категорию'),
  amount: z.preprocess(
    (val) => (val === '' || val === undefined || val === null ? undefined : val),
    z
      .number({ message: 'Введите сумму бюджета' })
      .gt(0, 'Сумма должна быть больше нуля'),
  ),
})

type BudgetFormValues = z.infer<typeof budgetSchema>

const MONTH_NAMES = [
  '', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
  'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]

interface Props {
  opened: boolean
  onClose: () => void
  // Месяц, на который создаётся бюджет (или редактируется существующий).
  // Передаётся из BudgetsPage — это месяц, который сейчас открыт.
  periodYear: number
  periodMonth: number
  // Если передан — режим редактирования (меняем только amount, категория
  // блокируется). Иначе — режим создания.
  budget?: BudgetWithProgress | null
  // ID категорий, на которые УЖЕ есть бюджет В ЭТОМ МЕСЯЦЕ — фильтруем их
  // из Select при создании. Иначе пользователь увидит 409 от бэка.
  existingCategoryIds?: number[]
}

export function BudgetFormModal({
  opened,
  onClose,
  periodYear,
  periodMonth,
  budget = null,
  existingCategoryIds = [],
}: Props) {
  const queryClient = useQueryClient()
  const isEdit = budget !== null

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => listCategoriesRequest(),
  })

  // initialValues.amount — undefined вместо 0: NumberInput покажет пустой
  // плейсхолдер, и пользователь не сможет «случайно отправить ноль».
  // Submit при пустом поле даст явную ошибку «Введите сумму бюджета».
  const form = useForm<{ category_id: string; amount: number | undefined }>({
    initialValues: {
      category_id: budget ? String(budget.category_id) : '',
      amount: budget ? Number(budget.amount) : undefined,
    },
    validate: zodResolver(budgetSchema),
  })

  // При повторном открытии модалки с другим budget — синхронизируем форму.
  useEffect(() => {
    if (opened) {
      form.setValues({
        category_id: budget ? String(budget.category_id) : '',
        amount: budget ? Number(budget.amount) : undefined,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, budget])

  const createMutation = useMutation({
    mutationFn: (values: BudgetFormValues) =>
      createBudgetRequest({
        category_id: Number(values.category_id),
        amount: values.amount,
        period_year: periodYear,
        period_month: periodMonth,
      }),
    onSuccess: () => {
      notifications.show({
        title: 'Бюджет создан',
        message: `Лимит на ${MONTH_NAMES[periodMonth]} ${periodYear} установлен`,
        color: 'green',
      })
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
      form.reset()
      onClose()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message: error.response?.data?.detail || 'Не удалось создать бюджет',
        color: 'red',
      })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (values: BudgetFormValues) =>
      updateBudgetRequest(budget!.id, { amount: values.amount }),
    onSuccess: () => {
      notifications.show({
        title: 'Бюджет обновлён',
        message: 'Новый лимит сохранён',
        color: 'green',
      })
      queryClient.invalidateQueries({ queryKey: ['budgets'] })
      onClose()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      notifications.show({
        title: 'Ошибка',
        message: error.response?.data?.detail || 'Не удалось обновить бюджет',
        color: 'red',
      })
    },
  })

  const handleClose = () => {
    form.reset()
    onClose()
  }

  const expenseCategoryOptions = buildCategoryOptions(categories, 'expense')
  const availableOptions = isEdit
    ? expenseCategoryOptions
    : expenseCategoryOptions.filter(
        (opt) => !existingCategoryIds.includes(Number(opt.value)),
      )

  // Тип параметра берём из form (amount: number | undefined), а не из zod-схемы:
  // Mantine типизирует onSubmit по initialValues, а не по результату resolver-а.
  // К моменту вызова валидация уже прошла, поэтому amount гарантированно number.
  const handleSubmit = (values: { category_id: string; amount: number | undefined }) => {
    const parsed: BudgetFormValues = {
      category_id: values.category_id,
      amount: values.amount as number,
    }
    if (isEdit) {
      updateMutation.mutate(parsed)
    } else {
      createMutation.mutate(parsed)
    }
  }

  // Если валидация формы не прошла — Mantine уже покажет ошибки под полями,
  // но дополнительно показываем toast, чтобы пользователь точно заметил
  // (поля могут быть ниже сгиба на маленьком экране).
  const handleValidationError = () => {
    notifications.show({
      title: 'Заполните форму',
      message: 'Проверьте поля — некоторые не заполнены или содержат ошибки.',
      color: 'yellow',
    })
  }

  const title = isEdit
    ? `Изменить бюджет (${MONTH_NAMES[periodMonth]} ${periodYear})`
    : `Новый бюджет на ${MONTH_NAMES[periodMonth]} ${periodYear}`

  return (
    <Modal opened={opened} onClose={handleClose} title={title} centered>
      <form onSubmit={form.onSubmit(handleSubmit, handleValidationError)}>
        <Stack>
          <Select
            label="Категория"
            description="Только расходные. Один бюджет на категорию в месяц."
            placeholder="Выберите категорию"
            data={availableOptions}
            searchable
            disabled={isEdit}
            required
            {...form.getInputProps('category_id')}
          />
          <NumberInput
            label="Лимит на месяц"
            description="Лимит в рублях. Траты в других валютах пересчитываются по курсу ЦБ РФ."
            placeholder="10 000"
            min={0}
            step={100}
            thousandSeparator=" "
            decimalScale={2}
            suffix=" ₽"
            required
            {...form.getInputProps('amount')}
          />
          {isEdit && (
            <Text size="xs" c="dimmed">
              Категорию и месяц изменить нельзя. Чтобы перенести лимит —
              удалите этот бюджет и создайте новый.
            </Text>
          )}
          <Button
            type="submit"
            loading={createMutation.isPending || updateMutation.isPending}
          >
            {isEdit ? 'Сохранить' : 'Создать'}
          </Button>
        </Stack>
      </form>
    </Modal>
  )
}
