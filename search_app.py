import pygame
import requests
import sys
import os

import math

from distance import lonlat_distance
from geo import reverse_geocode
from bis import find_business


# Подобранные константы для поведения карты.
LAT_STEP = 0.002  # Шаги при движении карты по широте и долготе
LON_STEP = 0.002
coord_to_geo_x = 0.0000428  # Пропорции пиксельных и географических координат.
coord_to_geo_y = 0.0000428


def ll(x, y):
    return "{0},{1}".format(x, y)


# Структура для хранения результатов поиска:
# координаты объекта, его название и почтовый индекс, если есть.

class SearchResult(object):
    def __init__(self, point, address, postal_code=None):
        self.point = point
        self.address = address
        self.postal_code = postal_code


# Параметры отображения карты:
# координаты, масштаб, найденные объекты и т.д.

class MapParams(object):
    # Параметры по умолчанию.
    def __init__(self):
        self.lat = 55.729738
        self.lon = 37.664777
        self.zoom = 15
        self.type = "map"

        self.search_result = None
        self.use_postal_code = False

        self.need_to_load = True

    def ll(self):
        return ll(self.lon, self.lat)

    def update(self, event):
        if event.key == pygame.K_PAGEUP  and self.zoom < 19:  # PG_UP
            self.zoom += 1
            self.need_to_load = True
        elif event.key == pygame.K_PAGEDOWN  and self.zoom > 2:  # PG_DOWN
            self.zoom -= 1
            self.need_to_load = True
        elif event.key == pygame.K_LEFT:  # LEFT_ARROW
            self.lon -= LON_STEP * math.pow(2, 15 - self.zoom)
            self.need_to_load = True
        elif event.key == pygame.K_RIGHT:  # RIGHT_ARROW
            self.lon += LON_STEP * math.pow(2, 15 - self.zoom)
            self.need_to_load = True
        elif event.key == pygame.K_UP and self.lat < 85:  # UP_ARROW
            self.lat += LAT_STEP * math.pow(2, 15 - self.zoom)
            self.need_to_load = True
        elif event.key == pygame.K_DOWN and self.lat > -85:  # DOWN_ARROW
            self.lat -= LAT_STEP * math.pow(2, 15 - self.zoom)
            self.need_to_load = True
        elif event.key == pygame.K_F1:  # F1
            self.type = "map"
            self.need_to_load = True
        elif event.key == pygame.K_F2:  # F2
            self.type = "sat"
            self.need_to_load = True
        elif event.key == pygame.K_F3:  # F3
            self.type = "sat,skl"
            self.need_to_load = True
        elif event.key == pygame.K_DELETE:  # DELETE
            self.search_result = None
            self.need_to_load = True
        elif event.key == pygame.K_INSERT:  # INSERT
            self.use_postal_code = not self.use_postal_code
            self.need_to_load = True

        if self.lon > 180: self.lon -= 360
        if self.lon < -180: self.lon += 360

    # Преобразование экранных координат в географические.
    def screen_to_geo(self, pos):
        dy = 225 - pos[1]
        dx = pos[0] - 300
        lx = self.lon + dx * coord_to_geo_x * math.pow(2, 15 - self.zoom)
        ly = self.lat + dy * coord_to_geo_y * math.cos(math.radians(self.lat)) * math.pow(2,
                                                                                          15 - self.zoom)
        return lx, ly

    # Добавить результат геопоиска на карту.
    def add_reverse_toponym_search(self, pos):
        point = pos
        toponym = reverse_geocode(ll(point[0], point[1]))
        self.search_result = SearchResult(
            point,
            toponym["metaDataProperty"]["GeocoderMetaData"]["text"] if toponym else None,
            toponym["metaDataProperty"]["GeocoderMetaData"]["Address"].get(
                "postal_code") if toponym else None)
        self.need_to_load = True

    # Добавить результат поиска организации на карту.
    def add_reverse_org_search(self, pos):
        self.search_result = None
        point = pos
        org = find_business(ll(point[0], point[1]))
        if not org:
            return

        org_point = org["geometry"]["coordinates"]
        org_lon = float(org_point[0])
        org_lat = float(org_point[1])

        # Проверяем, что найденный объект не дальше 50м от места клика.
        if lonlat_distance((org_lon, org_lat), point) <= 50:
            self.search_result = SearchResult(point, org["properties"]["CompanyMetaData"]["name"])
        self.need_to_load = True


# Создание карты с соответствующими параметрами.
def load_map(mp):
    map_request = "http://static-maps.yandex.ru/1.x/?ll={ll}&z={z}&l={type}".format(ll=mp.ll(),
                                                                                    z=mp.zoom,
                                                                                    type=mp.type)
    if mp.search_result:
        map_request += "&pt={0},{1},pm2grm".format(mp.search_result.point[0],
                                                   mp.search_result.point[1])

    response = requests.get(map_request)
    if not response:
        print("Ошибка выполнения запроса:")
        print(map_request)
        print("Http статус:", response.status_code, "(", response.reason, ")")
        sys.exit(1)

    # Запишем полученное изображение в файл.
    map_file = "map.png"
    try:
        with open(map_file, "wb") as file:
            file.write(response.content)
    except IOError as ex:
        print("Ошибка записи временного файла:", ex)
        sys.exit(2)

    return map_file


# поле ввода адреса
class InputBox:
    def __init__(self):
        self.active = False
        self.text = ''

    def update(self, event, mp: MapParams):
        if event.key == pygame.K_TAB:
            self.active = not self.active
            if not self.active:
                self.text = ''
        elif self.active:
            if event.key == pygame.K_RETURN:
                if self.text != '':
                    rj = requests.get(f"http://geocode-maps.yandex.ru/1.x/"
                                      f"?apikey=40d1649f-0493-4b70-98ba-98533de7710b"
                                      f"&geocode={self.text}"
                                      f"&format=json").json()
                    point = rj['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['Point']['pos']
                    mp.lon, mp.lat = [float(x) for x in point.split()]
                    mp.add_reverse_toponym_search((mp.lon, mp.lat))
                    self.active = False
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                letter = event.unicode
                self.text += letter

    def render(self, surface: pygame.Surface):
        width, height = surface.get_size()

        phase_offset = 100*(1-self.active)

        rectwidth = (600)
        rectheight = (32)+2
        pygame.draw.rect(surface, 'white', (0, 450-rectheight+phase_offset, rectwidth, rectheight), 0, 1)
        pygame.draw.rect(surface, 'black', (0, 450-rectheight+phase_offset, rectwidth, rectheight), 1, 1)

        txt = render_text(self.text)

        surface.blit(txt, (1, 450-rectheight+phase_offset+(rectheight-txt.get_height())//2))

ib = InputBox()

# Создание холста с текстом.
def render_text(text):
    font = pygame.font.Font(None, 30)
    return font.render(text, 1, (100, 0, 100))


def main():
    pygame.init()
    screen = pygame.display.set_mode((600, 450))

    default_font = pygame.font.Font(None, 30)

    # Заводим объект, в котором будем хранить все параметры отрисовки карты.
    mp = MapParams()

    stop = False
    while not stop:
        #event = pygame.event.wait()
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                stop = True
            elif event.type == pygame.KEYDOWN:
                ib.update(event, mp)
                mp.update(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # LEFT_MOUSE_BUTTON
                    mp.add_reverse_toponym_search(mp.screen_to_geo(event.pos))
                elif event.button == 3:  # RIGHT_MOUSE_BUTTON
                    mp.add_reverse_org_search(mp.screen_to_geo(event.pos))
            else:
                continue

        if mp.need_to_load:
            map_file = load_map(mp)
            mp.need_to_load = False

        screen.blit(pygame.image.load(map_file), (0, 0))

        if mp.search_result:
            if mp.use_postal_code and mp.search_result.postal_code:
                text = render_text(mp.search_result.postal_code + ", " + mp.search_result.address)
            else:
                text = render_text(mp.search_result.address)
            screen.blit(text, (20, 380))

        ib.render(screen)

        pygame.display.flip()

    pygame.quit()
    os.remove(map_file)


if __name__ == "__main__":
    main()
