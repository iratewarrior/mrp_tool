import pandas as pd
import streamlit as st

# Функция для нахождения всех аналогов для конкретного кода
def find_analogs(er_code, df_analogs):
    analogs = df_analogs[(df_analogs['Материал.Код'] == er_code) | 
                         (df_analogs['Аналог.Код'] == er_code)]
    all_codes = set(analogs['Материал.Код'].tolist() + analogs['Аналог.Код'].tolist())
    all_codes.discard(er_code)
    return list(all_codes)

# Функция для подсчета суммарного остатка по каждому коду и его аналогам
def calculate_aggregated_stock(df_specs, df_analogs, df_stocks, excluded_codes=[]):
    aggregated_stocks = {}
    for code in df_specs['Код']:
        if code not in excluded_codes:
            all_codes = [code] + find_analogs(code, df_analogs)
            total_stock = df_stocks[df_stocks['Код'].isin(all_codes)]['В наличии'].sum()
            aggregated_stocks[code] = total_stock
        else:
            aggregated_stocks[code] = 0  # Установить 0 для исключенных компонентов
    return aggregated_stocks

# Функция для расчета минимального количества продукта, которое можно собрать
def calculate_production_capacity(df_specs, df_analogs, df_stocks, excluded_codes=[]):
    capacity = {}
    for product in df_specs['Продукт'].unique():
        product_specs = df_specs[df_specs['Продукт'] == product]
        min_capacity = float('inf')
        for _, row in product_specs.iterrows():
            if row['Код'] not in excluded_codes:
                analogs = find_analogs(row['Код'], df_analogs)
                total_stock = df_stocks[df_stocks['Код'].isin([row['Код']] + analogs)]['В наличии'].sum()
                current_capacity = total_stock // row['Количество на изделие']
                if current_capacity < min_capacity:
                    min_capacity = current_capacity
        capacity[product] = min_capacity if min_capacity != float('inf') else 0
    return capacity

# Функция для расчета необходимых к дозакупке компонентов
def calculate_additional_requirements(df_specs, df_stocks, df_analogs, df_overuse, target_qty, aggregated_stocks):
    requirements = {}
    for product, qty in target_qty.items():
        if qty == 0:
            continue
        product_specs = df_specs[df_specs['Продукт'] == product]
        for _, row in product_specs.iterrows():
            needed = qty * row['Количество на изделие']
            excess_rate = df_overuse.loc[df_overuse['Код'] == row['Код'], 'Коэффициент брака производство']
            needed *= (1 + excess_rate.iloc[0] if not excess_rate.empty else 1)
            available = aggregated_stocks.get(row['Код'], 0)
            additional_required = needed - available
            if additional_required > 0:
                if row['Код'] in requirements:
                    requirements[row['Код']]['Дополнительно'] += additional_required
                else:
                    requirements[row['Код']] = {
                        'Описание': row['Описание'],
                        'Дополнительно': additional_required
                    }
    
    if requirements:
        requirements_df = pd.DataFrame.from_dict(requirements, orient='index').reset_index().rename(columns={'index': 'Код'})
        requirements_df['Дополнительно'] = requirements_df['Дополнительно'].fillna(0).astype(float).round(2)
        return requirements_df
    else:
        return pd.DataFrame(columns=['Код', 'Описание', 'Дополнительно'])

# Загрузка данных
df_specs = pd.read_excel('00_спецификации.xlsx')
df_analogs = pd.read_excel('01_аналоги.xlsx').drop_duplicates()
df_stocks = pd.read_excel('02_остатки_ERP.xlsx')
df_overuse = pd.read_excel('03_перерасход.xlsx')

# Интерфейс пользователя в Streamlit
st.set_page_config(page_title="Планирование материальных потребностей", layout="wide")
st.title('Планирование материальных потребностей (MRP)')

# Боковая панель для ввода данных
st.sidebar.title('Настройки')

# Ввод целевого количества продуктов в боковой панели
target_qty = {}
for product in df_specs['Продукт'].unique():
    target_qty[product] = st.sidebar.number_input(f'Целевое количество "{product}"', min_value=0, key=product)

# Список исключенных компонентов
if 'excluded_codes' not in st.session_state:
    st.session_state['excluded_codes'] = []

# Обработка клика на строку в таблице
def handle_click():
    selected_codes = st.session_state['selected_codes']
    st.session_state['excluded_codes'] = selected_codes

# Кнопка для сброса исключенных компонентов
if st.sidebar.button('Сбросить исключенные компоненты'):
    st.session_state['excluded_codes'] = []

# Агрегация остатков комплектующих с учетом аналогов
aggregated_stocks = calculate_aggregated_stock(df_specs, df_analogs, df_stocks, st.session_state['excluded_codes'])
df_specs['Агрегированные остатки'] = df_specs['Код'].map(aggregated_stocks).round(2)
df_specs['Входимость в 1 изделие'] = df_specs['Количество на изделие']
df_specs['Комплектов'] = (df_specs['Агрегированные остатки'] // df_specs['Количество на изделие']).round(2)

# Фильтр для отображения агрегированных остатков от меньшего к большему
df_specs_sorted = df_specs.sort_values(by='Агрегированные остатки')

# Расчет минимальной возможности производства на основе текущих остатков
production_capacity = calculate_production_capacity(df_specs, df_analogs, df_stocks, st.session_state['excluded_codes'])

# Минимальное количество каждого продукта, которое можно собрать
st.subheader('Минимальное количество каждого продукта, которое можно собрать:')
styled_capacity_df = pd.DataFrame.from_dict(production_capacity, orient='index', columns=['Минимальное количество']).round(2)
st.dataframe(styled_capacity_df.applymap(lambda x: '{:,.0f}'.format(x).replace(',', ' ')), use_container_width=True)

# Выбор продукта для отображения агрегированных остатков в боковой панели
selected_product = st.sidebar.selectbox('Выберите продукт для просмотра остатков комплектующих', df_specs['Продукт'].unique())
df_selected_product = df_specs[df_specs['Продукт'] == selected_product]

st.subheader(f'Агрегированные остатки для продукта {selected_product}')
selected_codes = st.multiselect('Исключить компоненты:', df_selected_product['Код'], default=st.session_state['excluded_codes'], key='selected_codes', on_change=handle_click)

# Применение форматирования только к числовым столбцам
numeric_columns = ['Агрегированные остатки', 'Входимость в 1 изделие', 'Комплектов']
df_selected_product[numeric_columns] = df_selected_product[numeric_columns].applymap(lambda x: '{:,.0f}'.format(x).replace(',', ' '))

st.dataframe(df_selected_product[['Код', 'Описание', 'Агрегированные остатки', 'Входимость в 1 изделие', 'Комплектов']], use_container_width=True)

# Проверка наличия целевых количеств перед расчетом дополнительных требований
if any(target_qty.values()):
    # Расчет необходимых к дозакупке компонентов
    additional_requirements_df = calculate_additional_requirements(df_specs, df_stocks, df_analogs, df_overuse, target_qty, aggregated_stocks)
    
    st.subheader('Необходимость в дозакупке компонентов для плана производства:')
    additional_requirements_df = additional_requirements_df[additional_requirements_df['Дополнительно'] > 0].fillna(0).astype({'Дополнительно': 'int'})
    additional_requirements_df['Дополнительно'] = additional_requirements_df['Дополнительно'].apply(lambda x: '{:,.0f}'.format(x).replace(',', ' '))
    st.dataframe(additional_requirements_df[['Код', 'Описание', 'Дополнительно']], use_container_width=True)
