import pandas as pd
import streamlit as st

# Функция для нахождения всех аналогов для конкретного кода
def find_analogs(er_code, df_analogs):
    analogs = df_analogs[(df_analogs['Материал.Код'] == er_code) | 
                         (df_analogs['Аналог.Код'] == er_code)]
    all_codes = set(analogs['Материал.Код'].tolist() + analogs['Аналог.Код'].tolist())
    all_codes.discard(er_code)
    return list(all_codes)

# Функция для подсчета суммарного остатка по каждому ЕР-коду и его аналогам
def calculate_aggregated_stock(df_specs, df_analogs, df_stocks):
    aggregated_stocks = {}
    for er_code in df_specs['Код']:
        all_codes = [er_code] + find_analogs(er_code, df_analogs)
        total_stock = df_stocks[df_stocks['Код'].isin(all_codes)]['В наличии'].sum()
        aggregated_stocks[er_code] = total_stock
    return aggregated_stocks

# Функция для расчета минимального количества продукта, которое можно собрать
def calculate_production_capacity(df_specs, df_analogs, df_stocks):
    capacity = {}
    for product in df_specs['Продукт'].unique():
        product_specs = df_specs[df_specs['Продукт'] == product]
        min_capacity = float('inf')
        for _, row in product_specs.iterrows():
            analogs = find_analogs(row['Код'], df_analogs)
            total_stock = df_stocks[df_stocks['Код'].isin([row['Код']] + analogs)]['В наличии'].sum()
            current_capacity = total_stock // row['Количество на изделие']
            if current_capacity < min_capacity:
                min_capacity = current_capacity
        capacity[product] = min_capacity
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

# Агрегация остатков комплектующих с учетом аналогов
aggregated_stocks = calculate_aggregated_stock(df_specs, df_analogs, df_stocks)
df_specs['Агрегированные остатки'] = df_specs['Код'].map(aggregated_stocks).round(2)

# Расчет минимальной возможности производства на основе текущих остатков
production_capacity = calculate_production_capacity(df_specs, df_analogs, df_stocks)

# Функция для стилизации DataFrame
def style_dataframe(df):
    styles = [
        dict(selector="tr:nth-child(even)", props=[("background-color", "#f2f2f2")]),
        dict(selector="tr:nth-child(odd)", props=[("background-color", "#ffffff")])
    ]
    df_styled = df.style.set_table_styles(styles)
    df_styled = df_styled.applymap(lambda x: 'color: red;' if x == 0 else '').format(precision=2)
    return df_styled

# Минимальное количество каждого продукта, которое можно собрать
st.subheader('Минимальное количество каждого продукта, которое можно собрать:')
styled_capacity_df = pd.DataFrame.from_dict(production_capacity, orient='index', columns=['Минимальное количество']).round(2)
st.dataframe(styled_capacity_df.style.set_table_styles([{
        'selector': 'thead th',
        'props': [('background-color', '#007bff'), ('color', 'white')]
    }, {
        'selector': 'tbody tr:nth-child(even)',
        'props': [('background-color', '#f2f2f2')]
    }, {
        'selector': 'tbody tr:nth-child(odd)',
        'props': [('background-color', '#ffffff')]
    }]).applymap(lambda x: 'color: red;' if x == 0 else ''), use_container_width=True)

# Выбор продукта для отображения агрегированных остатков в боковой панели
selected_product = st.sidebar.selectbox('Выберите продукт для просмотра остатков комплектующих', df_specs['Продукт'].unique())
df_selected_product = df_specs[df_specs['Продукт'] == selected_product]

st.subheader(f'Агрегированные остатки для продукта {selected_product}')
st.dataframe(df_selected_product[['Код', 'Описание', 'Агрегированные остатки']].round(2).style.set_table_styles([{
        'selector': 'thead th',
        'props': [('background-color', '#007bff'), ('color', 'white')]
    }, {
        'selector': 'tbody tr:nth-child(even)',
        'props': [('background-color', '#f2f2f2')]
    }, {
        'selector': 'tbody tr:nth-child(odd)',
        'props': [('background-color', '#ffffff')]
    }]).applymap(lambda x: 'color: red;' if x == 0 else ''), use_container_width=True)

# Проверка наличия целевых количеств перед расчетом дополнительных требований
if any(target_qty.values()):
    # Расчет необходимых к дозакупке компонентов
    additional_requirements_df = calculate_additional_requirements(df_specs, df_stocks, df_analogs, df_overuse, target_qty, aggregated_stocks)
    
    st.subheader('Необходимость в дозакупке компонентов для плана производства:')
    additional_requirements_df = additional_requirements_df[additional_requirements_df['Дополнительно'] > 0].round(2)
    st.dataframe(additional_requirements_df[['Код', 'Описание', 'Дополнительно']].style.set_table_styles([{
            'selector': 'thead th',
            'props': [('background-color', '#007bff'), ('color', 'white')]
        }, {
            'selector': 'tbody tr:nth-child(even)',
            'props': [('background-color', '#f2f2f2')]
        }, {
            'selector': 'tbody tr:nth-child(odd)',
            'props': [('background-color', '#ffffff')]
        }]).applymap(lambda x: 'color: red;' if x == 0 else ''), use_container_width=True)

# Дополнительная стилизация с использованием CSS
st.markdown("""
    <style>
    /* Общий стиль страницы */
    body {
        font-family: 'Arial', sans-serif;
        background-color: #f7f9fc;
    }

    /* Стиль боковой панели */
    .sidebar .sidebar-content {
        background-color: #ffffff;
        border-right: 1px solid #e0e0e0;
    }

    .sidebar .sidebar-content h1, .sidebar .sidebar-content h2, .sidebar .sidebar-content h3, .sidebar .sidebar-content h4, .sidebar .sidebar-content h5, .sidebar .sidebar-content h6 {
        color: #007bff;
    }

    /* Стиль заголовков */
    .css-10trblm {
        color: #007bff;
        font-weight: bold;
    }

    .css-1v3fvcr h2 {
        color: #007bff;
    }

    /* Стиль таблиц */
    .css-1l269bu th {
        background-color: #007bff !important;
        color: white !important;
    }

    .css-1l269bu tr:nth-child(even) {
        background-color: #f2f2f2 !important;
    }

    .css-1l269bu tr:nth-child(odd) {
        background-color: #ffffff !important;
    }

    .css-1l269bu td {
        border-bottom: 1px solid #dee2e6 !important;
    }
    </style>
    """, unsafe_allow_html=True)
